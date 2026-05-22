from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.models import SubtitleSegment, TranscriptionResult

DEFAULT_WHISPER_MODEL = "medium"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WHISPER_CPP_CLI_CANDIDATES = ("whisper-cli", "whisper.cpp", "main")
LOCAL_WHISPER_CPP_CLI_CANDIDATES = (
    PROJECT_ROOT / "vendor" / "whisper.cpp" / "build" / "bin" / "whisper-cli",
    PROJECT_ROOT / "vendor" / "whisper.cpp" / "build" / "bin" / "main",
)


class TranscriptionUnavailable(RuntimeError):
    pass


class TranscriptionFailed(RuntimeError):
    pass


def transcribe_video(video_path: Path) -> TranscriptionResult:
    audio_path: Path | None = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        temp_dir = tempfile.TemporaryDirectory(prefix="subgen-audio-")
        audio_path = Path(temp_dir.name) / "audio.wav"
        extract_audio(video_path, audio_path)

        cli_result = _transcribe_with_whisper_cpp(audio_path)
        if cli_result is not None:
            return cli_result

        try:
            return _transcribe_with_faster_whisper(audio_path)
        except ModuleNotFoundError:
            pass

        try:
            return _transcribe_with_openai_whisper(audio_path)
        except ModuleNotFoundError:
            pass

        raise TranscriptionUnavailable(
            "No local transcription backend is available. Install whisper.cpp, faster-whisper, or openai-whisper. "
            "For whisper.cpp, use the bundled vendor/whisper.cpp build and models/ggml-medium.bin, "
            "or set WHISPER_CPP_CLI and WHISPER_CPP_MODEL."
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def extract_audio(video_path: Path, audio_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise TranscriptionUnavailable("ffmpeg is required to extract audio from video files.")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(audio_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "ffmpeg failed to extract audio."
        raise TranscriptionFailed(stderr)


def probe_duration_seconds(media_path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return None
    try:
        return float(completed.stdout.strip())
    except ValueError:
        return None


def _transcribe_with_faster_whisper(audio_path: Path) -> TranscriptionResult:
    from faster_whisper import WhisperModel

    model_name = os.getenv("SUBGEN_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    device = os.getenv("SUBGEN_WHISPER_DEVICE", "auto")
    compute_type = os.getenv("SUBGEN_WHISPER_COMPUTE_TYPE", "default")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=int(os.getenv("SUBGEN_WHISPER_BEAM_SIZE", "5")),
        vad_filter=_env_bool("SUBGEN_WHISPER_VAD", default=False),
    )
    segments = [
        SubtitleSegment(start=float(segment.start), end=float(segment.end), text=segment.text.strip())
        for segment in segments_iter
    ]
    if not segments:
        raise TranscriptionFailed("The transcription model returned no subtitle segments.")
    return TranscriptionResult(
        language=info.language or "unknown",
        language_probability=getattr(info, "language_probability", None),
        duration_seconds=getattr(info, "duration", None) or probe_duration_seconds(audio_path),
        segments=segments,
        backend=f"faster-whisper:{model_name}",
    )


def _transcribe_with_openai_whisper(audio_path: Path) -> TranscriptionResult:
    import whisper

    model_name = os.getenv("SUBGEN_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), task="transcribe", fp16=False)
    segments = [
        SubtitleSegment(start=float(segment["start"]), end=float(segment["end"]), text=str(segment["text"]).strip())
        for segment in result.get("segments", [])
    ]
    if not segments:
        raise TranscriptionFailed("The transcription model returned no subtitle segments.")
    return TranscriptionResult(
        language=result.get("language") or "unknown",
        language_probability=None,
        duration_seconds=probe_duration_seconds(audio_path),
        segments=segments,
        backend=f"openai-whisper:{model_name}",
    )


def _transcribe_with_whisper_cpp(audio_path: Path) -> TranscriptionResult | None:
    cli_path = _resolve_whisper_cpp_cli()
    model_path = _resolve_whisper_cpp_model()
    if cli_path is None or model_path is None:
        return None

    with tempfile.TemporaryDirectory(prefix="subgen-whispercpp-") as temp_dir:
        output_prefix = Path(temp_dir) / "transcript"
        base_command = [
            str(cli_path),
            "-m",
            str(model_path),
            "-f",
            str(audio_path),
            "-l",
            "auto",
            "-oj",
            "-of",
            str(output_prefix),
        ]
        command = [*base_command]
        if _env_bool("WHISPER_CPP_NO_GPU", default=False):
            command.append("-ng")
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0 and "-ng" not in command and _is_whisper_cpp_gpu_failure(completed):
            command = [*base_command, "-ng"]
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip() or "whisper.cpp failed."
            raise TranscriptionFailed(stderr)
        json_path = output_prefix.with_suffix(".json")
        if not json_path.exists():
            raise TranscriptionFailed("whisper.cpp did not produce JSON output.")
        data = json.loads(json_path.read_text(encoding="utf-8"))
    model_name = os.getenv("WHISPER_CPP_MODEL_NAME", DEFAULT_WHISPER_MODEL)
    return _parse_whisper_cpp_json(data, audio_path, model_name=model_name)


def _resolve_whisper_cpp_cli() -> Path | None:
    configured = os.getenv("WHISPER_CPP_CLI")
    if configured:
        resolved = shutil.which(configured) or configured
        path = Path(resolved)
        if path.exists():
            return path
        raise TranscriptionUnavailable(f"WHISPER_CPP_CLI does not point to an executable: {configured}")

    for candidate in LOCAL_WHISPER_CPP_CLI_CANDIDATES:
        if candidate.exists():
            return candidate
    for candidate in WHISPER_CPP_CLI_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return Path(resolved)
    return None


def _resolve_whisper_cpp_model() -> Path | None:
    configured = os.getenv("WHISPER_CPP_MODEL")
    if configured:
        path = Path(configured)
        if path.exists():
            return path
        raise TranscriptionUnavailable(f"WHISPER_CPP_MODEL does not exist: {configured}")

    model_name = os.getenv("WHISPER_CPP_MODEL_NAME", DEFAULT_WHISPER_MODEL)
    model_dir = Path(os.getenv("WHISPER_CPP_MODEL_DIR", str(PROJECT_ROOT / "models")))
    candidate = model_dir / f"ggml-{model_name}.bin"
    if candidate.exists():
        return candidate
    return None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_whisper_cpp_gpu_failure(completed: subprocess.CompletedProcess[str]) -> bool:
    output = f"{completed.stderr}\n{completed.stdout}".lower()
    return "ggml_metal" in output or "failed to allocate buffer" in output or "no gpu found" in output


def _parse_whisper_cpp_json(data: dict[str, Any], audio_path: Path, model_name: str = DEFAULT_WHISPER_MODEL) -> TranscriptionResult:
    segments: list[SubtitleSegment] = []
    for item in data.get("transcription", []):
        timestamps = item.get("timestamps", {})
        start = _timestamp_to_seconds(timestamps.get("from"))
        end = _timestamp_to_seconds(timestamps.get("to"))
        text = str(item.get("text", "")).strip()
        if text:
            segments.append(SubtitleSegment(start=start, end=end, text=text))
    if not segments:
        raise TranscriptionFailed("whisper.cpp returned no subtitle segments.")
    result = data.get("result", {})
    language = result.get("language") or data.get("language") or "unknown"
    return TranscriptionResult(
        language=language,
        language_probability=None,
        duration_seconds=probe_duration_seconds(audio_path),
        segments=segments,
        backend=f"whisper.cpp:{model_name}",
    )


def _timestamp_to_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    parts = value.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        return float(value)
    except ValueError:
        return 0.0

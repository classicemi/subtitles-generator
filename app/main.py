from __future__ import annotations

import json
import mimetypes
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.models import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, SubtitleSegment, TranscriptionResult, utc_now_iso
from app.storage import TaskStore
from app.subtitles import render_srt, render_vtt
from app.transcription import TranscriptionFailed, TranscriptionUnavailable, transcribe_video
from app.translation import SUPPORTED_LANGUAGES, TranslationModelUnavailable, translate_segments


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
PLAYBACK_DIR = DATA_DIR / "playback"
DB_PATH = DATA_DIR / "tasks.sqlite3"

ALLOWED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

store = TaskStore(DB_PATH, DATA_DIR)
app = FastAPI(title="Local Subtitle Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


def _safe_filename(filename: str) -> str:
    candidate = Path(filename).name.strip() or "video"
    candidate = re.sub(r"[^A-Za-z0-9._ -]", "_", candidate)
    return candidate[:180]


@app.post("/api/tasks", status_code=201)
async def create_task(background_tasks: BackgroundTasks, video: UploadFile = File(...)) -> dict[str, object]:
    original_name = _safe_filename(video.filename or "video")
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported media type. Allowed extensions: {allowed}")

    task_id = uuid.uuid4().hex
    task_dir = UPLOADS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    stored_path = task_dir / original_name

    with stored_path.open("wb") as output:
        shutil.copyfileobj(video.file, output)

    task = store.create(task_id=task_id, filename=original_name, stored_path=stored_path)
    background_tasks.add_task(process_task, task_id)
    return task.as_dict()


@app.get("/api/tasks")
def list_tasks() -> dict[str, list[dict[str, object]]]:
    return {"tasks": [task.as_dict() for task in store.list()]}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    try:
        return store.get(task_id).as_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post("/api/tasks/{task_id}/regenerate", status_code=202)
def regenerate_task(task_id: str, background_tasks: BackgroundTasks) -> dict[str, object]:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    if task.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Task is already running")
    if not task.stored_path.exists():
        raise HTTPException(status_code=404, detail="Source media not found")

    task = store.update(
        task_id,
        status="queued",
        progress=0,
        language=None,
        language_probability=None,
        duration_seconds=None,
        backend=None,
        error=None,
        subtitle_srt_path=None,
        subtitle_vtt_path=None,
        transcript_json_path=None,
        completed_at=None,
    )
    background_tasks.add_task(process_task, task_id)
    return task.as_dict()


@app.delete("/api/tasks/{task_id}", status_code=200)
def delete_task(task_id: str) -> dict[str, str]:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    store.delete(task_id)

    for directory in (
        UPLOADS_DIR / task_id,
        ARTIFACTS_DIR / task_id,
        PLAYBACK_DIR / task_id,
    ):
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=False)

    return {"detail": "Task deleted"}


@app.head("/api/tasks/{task_id}/media")
@app.get("/api/tasks/{task_id}/media")
def play_source_media(task_id: str) -> FileResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    media_path = _playback_media_path(task_id, task.stored_path)
    if not media_path.exists():
        media_path = task.stored_path
    if not media_path.exists():
        raise HTTPException(status_code=404, detail="Source media not found")
    media_type = mimetypes.guess_type(media_path.name)[0] or "application/octet-stream"
    return FileResponse(path=media_path, media_type=media_type)


@app.get("/api/tasks/{task_id}/download/{artifact_type}")
def download_artifact(task_id: str, artifact_type: Literal["srt", "vtt", "json", "translated_srt", "translated_vtt", "translated_json"]) -> FileResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    artifact_path = {
        "srt": task.subtitle_srt_path,
        "vtt": task.subtitle_vtt_path,
        "json": task.transcript_json_path,
        "translated_srt": task.translated_srt_path,
        "translated_vtt": task.translated_vtt_path,
        "translated_json": task.translated_json_path,
    }[artifact_type]
    if artifact_path is None or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    media_type = {
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "json": "application/json",
        "translated_srt": "application/x-subrip",
        "translated_vtt": "text/vtt",
        "translated_json": "application/json",
    }[artifact_type]
    return FileResponse(path=artifact_path, filename=artifact_path.name, media_type=media_type)


@app.get("/api/tasks/{task_id}/languages")
def translation_languages(task_id: str) -> dict[str, object]:
    try:
        store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return {"languages": SUPPORTED_LANGUAGES, "source_language": None}


class TranslateRequest(BaseModel):
    target_lang: str


@app.post("/api/tasks/{task_id}/translate")
def translate_task(task_id: str, body: TranslateRequest) -> dict[str, object]:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    if task.status != "succeeded":
        raise HTTPException(status_code=409, detail="Task must be in succeeded state to translate")

    if task.transcript_json_path is None or not task.transcript_json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript JSON not found")

    valid_codes = {lang["code"] for lang in SUPPORTED_LANGUAGES}
    if body.target_lang not in valid_codes:
        raise HTTPException(status_code=400, detail=f"Unsupported target language: {body.target_lang}")

    try:
        transcript_data = json.loads(task.transcript_json_path.read_text(encoding="utf-8"))
        segments = [
            SubtitleSegment(start=seg["start"], end=seg["end"], text=seg["text"])
            for seg in transcript_data.get("segments", [])
        ]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Failed to read transcript data") from exc

    try:
        translated = translate_segments(segments, task.language or "en", body.target_lang)
    except TranslationModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}") from exc

    translated_result = TranscriptionResult(
        language=body.target_lang,
        language_probability=1.0,
        segments=translated,
        backend="nllb-200-distilled-600M",
        duration_seconds=task.duration_seconds,
    )

    artifact_dir = ARTIFACTS_DIR / task_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(task.filename).stem or task_id
    safe_stem = _safe_filename(stem)
    safe_lang = _safe_filename(body.target_lang)
    srt_path = artifact_dir / f"{safe_stem}.{safe_lang}.translated.srt"
    vtt_path = artifact_dir / f"{safe_stem}.{safe_lang}.translated.vtt"
    json_path = artifact_dir / f"{safe_stem}.{safe_lang}.transcript.json"

    srt_path.write_text(render_srt(translated), encoding="utf-8")
    vtt_path.write_text(render_vtt(translated), encoding="utf-8")
    payload = {
        "task_id": task_id,
        "source_filename": task.filename,
        "generated_at": utc_now_iso(),
        "target_language": body.target_lang,
        **translated_result.as_dict(),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    target_name = next(
        (lang["name"] for lang in SUPPORTED_LANGUAGES if lang["code"] == body.target_lang),
        body.target_lang,
    )
    task = store.update(
        task_id,
        translated_language=f"{target_name} ({body.target_lang})",
        translated_srt_path=srt_path,
        translated_vtt_path=vtt_path,
        translated_json_path=json_path,
    )

    return task.as_dict()


def process_task(task_id: str) -> None:
    try:
        task = store.update(task_id, status="running", progress=10, error=None)
        prepare_playback_media(task_id, task.stored_path)
        result = transcribe_video(task.stored_path)
        artifact_paths = write_artifacts(task_id, task.filename, result)
        store.update(
            task_id,
            status="succeeded",
            progress=100,
            language=result.language,
            language_probability=result.language_probability,
            duration_seconds=result.duration_seconds,
            backend=result.backend,
            subtitle_srt_path=artifact_paths["srt"],
            subtitle_vtt_path=artifact_paths["vtt"],
            transcript_json_path=artifact_paths["json"],
            completed_at=utc_now_iso(),
            error=None,
        )
    except (TranscriptionUnavailable, TranscriptionFailed, RuntimeError, OSError) as exc:
        store.update(
            task_id,
            status="failed",
            progress=100,
            error=str(exc),
            completed_at=utc_now_iso(),
        )


def prepare_playback_media(task_id: str, source_path: Path) -> Path:
    if source_path.suffix.lower() not in VIDEO_EXTENSIONS:
        return source_path

    output_path = _playback_media_path(task_id, source_path)
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    if shutil.which("ffmpeg") is None:
        return source_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:v?",
        "-map",
        "0:a?",
        "-sn",
        "-dn",
        "-c",
        "copy",
        str(output_path),
    ]
    completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if completed.returncode != 0:
        output_path.unlink(missing_ok=True)
        return source_path
    return output_path


def _playback_media_path(task_id: str, source_path: Path) -> Path:
    safe_stem = _safe_filename(source_path.stem or task_id)
    suffix = source_path.suffix.lower() or ".media"
    return PLAYBACK_DIR / task_id / f"{safe_stem}.clean{suffix}"


def write_artifacts(task_id: str, filename: str, result: TranscriptionResult) -> dict[str, Path]:
    artifact_dir = ARTIFACTS_DIR / task_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(filename).stem or task_id
    safe_stem = _safe_filename(stem)
    safe_language = _safe_filename(result.language or "unknown")
    srt_path = artifact_dir / f"{safe_stem}.{safe_language}.srt"
    vtt_path = artifact_dir / f"{safe_stem}.{safe_language}.vtt"
    json_path = artifact_dir / f"{safe_stem}.transcript.json"

    srt_path.write_text(render_srt(result.segments), encoding="utf-8")
    vtt_path.write_text(render_vtt(result.segments), encoding="utf-8")
    payload = {
        "task_id": task_id,
        "source_filename": filename,
        "generated_at": utc_now_iso(),
        **result.as_dict(),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"srt": srt_path, "vtt": vtt_path, "json": json_path}


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not found")

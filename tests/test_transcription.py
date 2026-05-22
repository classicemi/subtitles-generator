from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import transcription
from app.models import SubtitleSegment, TranscriptionResult


class TranscriptionBackendSelectionTests(unittest.TestCase):
    def test_prefers_whisper_cpp_before_python_backends(self) -> None:
        result = TranscriptionResult(
            language="en",
            language_probability=None,
            duration_seconds=1.0,
            backend="whisper.cpp:medium",
            segments=[SubtitleSegment(start=0, end=1, text="hello")],
        )

        with patch.object(transcription, "extract_audio"), patch.object(
            transcription, "_transcribe_with_whisper_cpp", return_value=result
        ), patch.object(transcription, "_transcribe_with_faster_whisper") as faster_whisper:
            actual = transcription.transcribe_video(Path("sample.mp4"))

        self.assertEqual(actual.backend, "whisper.cpp:medium")
        faster_whisper.assert_not_called()

    def test_default_whisper_cpp_model_is_medium(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"WHISPER_CPP_MODEL_DIR": temp_dir},
            clear=True,
        ):
            model_path = Path(temp_dir) / "ggml-medium.bin"
            model_path.write_bytes(b"model")

            self.assertEqual(transcription._resolve_whisper_cpp_model(), model_path)

    def test_resolves_project_local_whisper_cpp_cli_before_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True), patch.object(
            transcription.shutil, "which", return_value="/usr/local/bin/whisper-cli"
        ):
            cli_path = Path(temp_dir) / "whisper-cli"
            cli_path.write_bytes(b"cli")

            with patch.object(transcription, "LOCAL_WHISPER_CPP_CLI_CANDIDATES", (cli_path,)):
                self.assertEqual(transcription._resolve_whisper_cpp_cli(), cli_path)

    def test_resolves_project_local_default_whisper_cpp_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            project_root = Path(temp_dir)
            model_path = project_root / "models" / "ggml-medium.bin"
            model_path.parent.mkdir()
            model_path.write_bytes(b"model")

            with patch.object(transcription, "PROJECT_ROOT", project_root):
                self.assertEqual(transcription._resolve_whisper_cpp_model(), model_path)

    def test_whisper_cpp_retries_without_gpu_on_metal_failure(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 1, "", "ggml_metal_buffer_init: error")

            output_prefix = Path(command[command.index("-of") + 1])
            output_prefix.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "result": {"language": "en"},
                        "transcription": [
                            {
                                "timestamps": {"from": "00:00:00.000", "to": "00:00:01.000"},
                                "text": "hello",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(transcription, "_resolve_whisper_cpp_cli", return_value=Path("/bin/whisper-cli")),
            patch.object(transcription, "_resolve_whisper_cpp_model", return_value=Path("/models/ggml-medium.bin")),
            patch.object(transcription.subprocess, "run", side_effect=fake_run),
            patch.object(transcription, "probe_duration_seconds", return_value=1.0),
        ):
            result = transcription._transcribe_with_whisper_cpp(Path("audio.wav"))

        self.assertEqual(result.backend, "whisper.cpp:medium")
        self.assertEqual(result.segments[0].text, "hello")
        self.assertNotIn("-ng", calls[0])
        self.assertIn("-ng", calls[1])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.models import SubtitleSegment, TranscriptionResult
from app.storage import TaskStore


class ApiFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.store = TaskStore(root / "tasks.sqlite3", root)
        self.patches = [
            patch.object(main, "store", self.store),
            patch.object(main, "UPLOADS_DIR", root / "uploads"),
            patch.object(main, "ARTIFACTS_DIR", root / "artifacts"),
            patch.object(main, "PLAYBACK_DIR", root / "playback"),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_upload_generates_and_downloads_subtitle_artifacts(self) -> None:
        result = TranscriptionResult(
            language="en",
            language_probability=0.98,
            duration_seconds=1.5,
            backend="test-backend",
            segments=[SubtitleSegment(start=0, end=1.5, text="Hello from the test.")],
        )

        with patch.object(main, "transcribe_video", return_value=result):
            response = self.client.post(
                "/api/tasks",
                files={"video": ("clip.mp4", b"not a real video", "video/mp4")},
            )

        self.assertEqual(response.status_code, 201)
        task_id = response.json()["id"]

        detail = self.client.get(f"/api/tasks/{task_id}").json()
        self.assertEqual(detail["status"], "succeeded")
        self.assertEqual(detail["language"], "en")
        self.assertEqual(detail["source"]["kind"], "video")
        self.assertEqual(detail["source"]["url"], f"/api/tasks/{task_id}/media")
        self.assertEqual(len(detail["artifacts"]), 3)

        task = self.store.get(task_id)
        clean_media_path = main._playback_media_path(task_id, task.stored_path)
        clean_media_path.parent.mkdir(parents=True, exist_ok=True)
        clean_media_path.write_bytes(b"clean video without subtitle streams")

        media_response = self.client.get(f"/api/tasks/{task_id}/media")
        self.assertEqual(media_response.status_code, 200)
        self.assertEqual(media_response.content, b"clean video without subtitle streams")

        media_head_response = self.client.head(f"/api/tasks/{task_id}/media")
        self.assertEqual(media_head_response.status_code, 200)
        self.assertEqual(media_head_response.headers["content-type"], "video/mp4")

        srt_response = self.client.get(f"/api/tasks/{task_id}/download/srt")
        self.assertEqual(srt_response.status_code, 200)
        self.assertIn("Hello from the test.", srt_response.text)

    def test_regenerates_subtitle_artifacts_for_existing_task(self) -> None:
        first_result = TranscriptionResult(
            language="en",
            language_probability=0.98,
            duration_seconds=1.5,
            backend="first-backend",
            segments=[SubtitleSegment(start=0, end=1.5, text="First subtitles.")],
        )
        second_result = TranscriptionResult(
            language="en",
            language_probability=0.99,
            duration_seconds=1.5,
            backend="second-backend",
            segments=[SubtitleSegment(start=0, end=1.5, text="Regenerated subtitles.")],
        )

        with patch.object(main, "transcribe_video", return_value=first_result):
            create_response = self.client.post(
                "/api/tasks",
                files={"video": ("clip.mp4", b"not a real video", "video/mp4")},
            )
        task_id = create_response.json()["id"]

        with patch.object(main, "transcribe_video", return_value=second_result):
            regenerate_response = self.client.post(f"/api/tasks/{task_id}/regenerate")

        self.assertEqual(regenerate_response.status_code, 202)
        detail = self.client.get(f"/api/tasks/{task_id}").json()
        self.assertEqual(detail["status"], "succeeded")
        self.assertEqual(detail["backend"], "second-backend")

        srt_response = self.client.get(f"/api/tasks/{task_id}/download/srt")
        self.assertEqual(srt_response.status_code, 200)
        self.assertIn("Regenerated subtitles.", srt_response.text)
        self.assertNotIn("First subtitles.", srt_response.text)

    def test_rejects_unsupported_file_extension(self) -> None:
        response = self.client.post(
            "/api/tasks",
            files={"video": ("notes.txt", b"hello", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

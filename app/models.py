from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SubtitleSegment:
    start: float
    end: float
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "text": self.text}


@dataclass(frozen=True)
class TranscriptionResult:
    language: str
    language_probability: float | None
    segments: list[SubtitleSegment]
    backend: str
    duration_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "language_probability": self.language_probability,
            "backend": self.backend,
            "duration_seconds": self.duration_seconds,
            "segments": [segment.as_dict() for segment in self.segments],
        }


@dataclass
class TaskRecord:
    id: str
    filename: str
    stored_path: Path
    status: str
    created_at: str
    updated_at: str
    progress: int = 0
    language: str | None = None
    language_probability: float | None = None
    duration_seconds: float | None = None
    backend: str | None = None
    error: str | None = None
    subtitle_srt_path: Path | None = None
    subtitle_vtt_path: Path | None = None
    transcript_json_path: Path | None = None
    completed_at: str | None = None
    artifacts: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        suffix = self.stored_path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            media_kind = "video"
        elif suffix in AUDIO_EXTENSIONS:
            media_kind = "audio"
        else:
            media_kind = "media"

        return {
            "id": self.id,
            "filename": self.filename,
            "source": {
                "filename": self.filename,
                "kind": media_kind,
                "url": f"/api/tasks/{self.id}/media",
            },
            "status": self.status,
            "progress": self.progress,
            "language": self.language,
            "language_probability": self.language_probability,
            "duration_seconds": self.duration_seconds,
            "backend": self.backend,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "artifacts": self.artifacts,
        }

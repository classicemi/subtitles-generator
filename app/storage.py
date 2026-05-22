from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from app.models import TaskRecord, utc_now_iso


STATUSES = {"queued", "running", "succeeded", "failed"}


class TaskStore:
    def __init__(self, db_path: Path, data_dir: Path) -> None:
        self.db_path = db_path
        self.data_dir = data_dir
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    language TEXT,
                    language_probability REAL,
                    duration_seconds REAL,
                    backend TEXT,
                    error TEXT,
                    subtitle_srt_path TEXT,
                    subtitle_vtt_path TEXT,
                    transcript_json_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)")

    def create(self, task_id: str, filename: str, stored_path: Path) -> TaskRecord:
        now = utc_now_iso()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, filename, stored_path, status, progress, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', 0, ?, ?)
                """,
                (task_id, filename, str(stored_path), now, now),
            )
        return self.get(task_id)

    def update(self, task_id: str, **fields: Any) -> TaskRecord:
        if not fields:
            return self.get(task_id)
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"Unsupported task status: {fields['status']}")
        fields["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [self._serialize_value(value) for value in fields.values()]
        values.append(task_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", values)
            if cursor.rowcount == 0:
                raise KeyError(task_id)
        return self.get(task_id)

    def get(self, task_id: str) -> TaskRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._row_to_task(row)

    def list(self) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        artifacts: list[dict[str, str]] = []
        if row["subtitle_srt_path"]:
            artifacts.append({"type": "srt", "label": "SRT subtitle", "filename": Path(row["subtitle_srt_path"]).name})
        if row["subtitle_vtt_path"]:
            artifacts.append({"type": "vtt", "label": "WebVTT subtitle", "filename": Path(row["subtitle_vtt_path"]).name})
        if row["transcript_json_path"]:
            artifacts.append({"type": "json", "label": "Transcript JSON", "filename": Path(row["transcript_json_path"]).name})

        return TaskRecord(
            id=row["id"],
            filename=row["filename"],
            stored_path=Path(row["stored_path"]),
            status=row["status"],
            progress=row["progress"],
            language=row["language"],
            language_probability=row["language_probability"],
            duration_seconds=row["duration_seconds"],
            backend=row["backend"],
            error=row["error"],
            subtitle_srt_path=self._optional_path(row["subtitle_srt_path"]),
            subtitle_vtt_path=self._optional_path(row["subtitle_vtt_path"]),
            transcript_json_path=self._optional_path(row["transcript_json_path"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            artifacts=artifacts,
        )

    @staticmethod
    def _optional_path(value: str | None) -> Path | None:
        return Path(value) if value else None

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        return value

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

from app.models import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, TranscriptionResult, utc_now_iso
from app.storage import TaskStore
from app.subtitles import render_srt, render_vtt
from app.transcription import TranscriptionFailed, TranscriptionUnavailable, transcribe_video


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
def download_artifact(task_id: str, artifact_type: Literal["srt", "vtt", "json"]) -> FileResponse:
    try:
        task = store.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    artifact_path = {
        "srt": task.subtitle_srt_path,
        "vtt": task.subtitle_vtt_path,
        "json": task.transcript_json_path,
    }[artifact_type]
    if artifact_path is None or not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    media_type = {
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "json": "application/json",
    }[artifact_type]
    return FileResponse(path=artifact_path, filename=artifact_path.name, media_type=media_type)


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

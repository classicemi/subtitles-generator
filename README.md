# Local Subtitle Generator

Web app for creating subtitle-generation tasks from local video or audio files. It stores each task, detects the spoken language through a local Whisper-compatible backend, writes subtitle artifacts, and exposes downloads for SRT, WebVTT, and transcript JSON.

## Quick Start

Requires `python3`, `node`, `cmake`, `git`, `curl`, and `ffmpeg` on `PATH`.

```bash
make setup    # install deps, build whisper.cpp, download model (~1.5 GB)
make start    # start backend (8000) + frontend (5173)
make stop     # stop both services
```

Open `http://127.0.0.1:5173` after `make start`.

To use a different model size (e.g. `tiny` for a faster CPU-only test):

```bash
make setup WHISPER_MODEL=tiny
```

## Run (manual)

Backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

The frontend is a separate Vite React app. The FastAPI service only exposes API, media, and artifact download routes.

`ffmpeg` must be available on `PATH` so the app can extract audio from video files.

## Local model backend

Recommended backend priority: `whisper.cpp`, then `faster-whisper`, then `openai-whisper`. The default model size is `medium`. Override Python Whisper backends with:

```bash
SUBGEN_WHISPER_MODEL=large-v3 uvicorn app.main:app --reload
```

For a faster CPU-only smoke test, use `SUBGEN_WHISPER_MODEL=tiny`.

The app tries transcription backends in this order:

1. `whisper.cpp`, using `WHISPER_CPP_CLI`/`WHISPER_CPP_MODEL`, the bundled `vendor/whisper.cpp/build/bin/whisper-cli` with `models/ggml-medium.bin`, or a `whisper-cli` on `PATH`
2. `faster-whisper`
3. `openai-whisper`

This workspace is set up for the bundled `whisper.cpp` deployment:

```bash
vendor/whisper.cpp/build/bin/whisper-cli
models/ggml-medium.bin
```

Example external whisper.cpp configuration:

```bash
WHISPER_CPP_CLI=/path/to/whisper-cli \
WHISPER_CPP_MODEL=/path/to/ggml-medium.bin \
uvicorn app.main:app --reload
```

If Metal/GPU initialization fails on macOS, the backend automatically retries `whisper.cpp` with `-ng`. You can force CPU mode with:

```bash
WHISPER_CPP_NO_GPU=1 uvicorn app.main:app --reload
```

## API

- `POST /api/tasks` with multipart field `video`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/regenerate`
- `GET /api/tasks/{task_id}/media`
- `GET /api/tasks/{task_id}/download/srt`
- `GET /api/tasks/{task_id}/download/vtt`
- `GET /api/tasks/{task_id}/download/json`

Generated files live under `data/artifacts/{task_id}`. Uploaded media and the SQLite database live under `data/`.

For video playback, the app prepares a clean playback copy under `data/playback/{task_id}` with soft subtitle streams stripped by `ffmpeg -sn`. The browser player then loads the generated WebVTT file as a separate subtitle track. Hardcoded subtitles burned into the pixels cannot be reliably removed automatically.

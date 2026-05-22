# AGENTS.md — Local Subtitle Generator

## Commands

```bash
make setup               # venv + pip install + clone/build whisper.cpp + download model ~1.5GB + npm install
make start               # frontend build → start backend:8000 + Vite dev server:5173
make stop                # kill both services via PID files in data/
make clean               # stop + rm .venv, node_modules, whisper.cpp, models, data/
make WHISPER_MODEL=tiny setup  # use smaller model (faster CPU-only test)
```

- `make start` **always runs `build-frontend` first** (tsc -b && vite build → `static/`).
- `static/` is **gitignored** — it's a build artifact.
- `npm run build` = `tsc -b && vite build` (output: `../static/`).

## Architecture

```
Browser → :5173 (Vite dev, proxies /api → :8000)
         → :8000 (FastAPI, serves built static/ SPA + API routes)
```

- **Backend**: `app/main.py` — FastAPI, uvicorn with `--reload`. API routes under `/api/tasks`.
- **Frontend**: `frontend/` — Vite + React 19 + React Router v7 + TypeScript.
- **Styling**: Single global CSS file at `frontend/src/styles.css` — no CSS modules/CSS-in-JS.
- **No test framework** currently configured.

## Transcription Backends (priority order)

1. **whisper.cpp** (bundled `vendor/whisper.cpp/build/bin/whisper-cli` + `models/ggml-medium.bin`)
2. **faster-whisper** (pip package, env: `SUBGEN_WHISPER_MODEL`)
3. **openai-whisper** (pip package, commented out in requirements.txt)

Env vars: `WHISPER_CPP_CLI`, `WHISPER_CPP_MODEL`, `WHISPER_CPP_NO_GPU=1` (force CPU), `SUBGEN_WHISPER_MODEL`.

## Translation

- Model: `facebook/nllb-200-distilled-600M` (~2.5 GB, downloaded on first use).
- Backend: `app/translation.py` — lazy-loads model, maps Whisper codes to FLORES-200, batch-translates segments.
- API: `GET /api/tasks/{id}/languages`, `POST /api/tasks/{id}/translate { target_lang }`, translated artifacts via `/download/translated_{srt,vtt,json}`.
- Frontend: language selector + translate button in task detail sidebar; translated VTT appears as a second subtitle track in the player.

## Data flow

- Upload → `data/uploads/{task_id}/` → ffmpeg extract audio → transcribe → artifacts in `data/artifacts/{task_id}/`
- Playback: `ffmpeg -sn` strips soft subs into `data/playback/{task_id}/`
- SQLite DB: `data/tasks.sqlite3`
- **`data/` is gitignored** — containing uploads, artifacts, playback, DB, PID files, logs.

## Frontend

- `react-router-dom` v7 — client-side routing with `<Link>`, `<useParams>`, `<useNavigate>`.
- Vite dev server proxies `/api` to `127.0.0.1:8000`.
- `tsc -b` uses project references (`tsconfig.json` → `tsconfig.node.json`).
- `frontend/vite.config.js` and `frontend/vite.config.d.ts` are gitignored build artifacts.

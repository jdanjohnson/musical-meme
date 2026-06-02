# DJ Set Planner

Analyze your music library and plan DJ sets using music theory — harmonic mixing, tension & release, energy arcs.

## Architecture

- **`analyzer/`** — Python audio analysis engine (FastAPI + librosa). Scans your music folders, detects BPM, musical key, energy level, and caches results in SQLite.
- **`web/`** — Next.js frontend. Library dashboard with Camelot wheel visualization, BPM histograms, and an interactive set builder.

## Quick Start

### 1. Start the analyzer backend

```bash
cd analyzer
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

### 2. Start the web frontend

```bash
cd web
npm install
npm run dev
```

### 3. Analyze your library

Open `http://localhost:3000`, point it at your music folder, and let it analyze. Results are cached — subsequent scans only process new/changed files.

## Features

- **Audio Analysis** — BPM detection, musical key detection, energy/loudness analysis, duration
- **Folder-aware** — respects your genre folder structure
- **Camelot Wheel** — visualize your library on the harmonic mixing wheel
- **Set Builder** — plan sets with harmonic compatibility scoring, energy arc templates, and "what's next" suggestions
- **Set Analysis** — score existing playlists on harmonic flow and energy programming
- **5000+ track support** — background processing with progress tracking

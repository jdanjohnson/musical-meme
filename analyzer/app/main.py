"""FastAPI backend — serves library data and runs analysis jobs."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import init_db, get_db, upsert_track, get_all_tracks, get_track_by_id, get_tracks_by_ids, get_analyzed_paths
from app.audio import scan_folder, analyze_track, file_hash
from app.theory import (
    score_transition,
    suggest_next_tracks,
    auto_generate_set,
    harmonic_relationship,
    camelot_distance,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track active scan jobs
active_jobs: dict[int, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="DJ Set Planner API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Models ---


class ScanRequest(BaseModel):
    folder_path: str


class ScanStatus(BaseModel):
    job_id: int
    status: str
    total_files: int
    processed_files: int
    skipped_files: int
    error_files: int
    current_file: str | None = None
    error_message: str | None = None


class SetGenerateRequest(BaseModel):
    start_track_id: int | None = None
    target_minutes: int = 60
    arc_type: str = "standard"
    bpm_range: float = 8.0
    genre_filter: str | None = None


class SuggestRequest(BaseModel):
    track_id: int
    position_in_set: float = 0.5
    arc_type: str = "standard"
    bpm_range: float = 8.0
    exclude_ids: list[int] = []
    limit: int = 20


class TransitionRequest(BaseModel):
    track_a_id: int
    track_b_id: int
    position_in_set: float = 0.5
    arc_type: str = "standard"


# --- Scan endpoints ---


@app.post("/api/scan", response_model=ScanStatus)
async def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    """Start scanning and analyzing a music folder."""
    import os
    if not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail=f"Folder not found: {req.folder_path}")

    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO scan_jobs (folder_path, status, started_at) VALUES (?, ?, ?)",
            (req.folder_path, "scanning", datetime.now(timezone.utc).isoformat()),
        )
        job_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    active_jobs[job_id] = {
        "status": "scanning",
        "total_files": 0,
        "processed_files": 0,
        "skipped_files": 0,
        "error_files": 0,
        "current_file": None,
    }

    background_tasks.add_task(run_scan, job_id, req.folder_path)

    return ScanStatus(
        job_id=job_id,
        status="scanning",
        total_files=0,
        processed_files=0,
        skipped_files=0,
        error_files=0,
    )


@app.get("/api/scan/{job_id}", response_model=ScanStatus)
async def get_scan_status(job_id: int):
    """Get the status of a scan job."""
    if job_id in active_jobs:
        job = active_jobs[job_id]
        return ScanStatus(job_id=job_id, **job)

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM scan_jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        return ScanStatus(
            job_id=row["id"],
            status=row["status"],
            total_files=row["total_files"],
            processed_files=row["processed_files"],
            skipped_files=row["skipped_files"],
            error_files=row["error_files"],
            error_message=row["error_message"],
        )
    finally:
        await db.close()


async def run_scan(job_id: int, folder_path: str) -> None:
    """Background task: scan folder and analyze tracks."""
    job = active_jobs[job_id]
    try:
        # Discover files
        files = scan_folder(folder_path)
        job["total_files"] = len(files)
        job["status"] = "analyzing"
        logger.info("Found %d audio files in %s", len(files), folder_path)

        # Get already-analyzed files
        db = await get_db()
        try:
            analyzed = await get_analyzed_paths(db)
        finally:
            await db.close()

        for filepath in files:
            try:
                # Check if already analyzed with same hash
                current_hash = file_hash(filepath)
                if filepath in analyzed and analyzed[filepath] == current_hash:
                    job["skipped_files"] += 1
                    job["processed_files"] += 1
                    continue

                job["current_file"] = filepath

                # Run CPU-heavy analysis in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, analyze_track, filepath, folder_path
                )

                # Save to DB
                db = await get_db()
                try:
                    await upsert_track(db, result.to_dict())
                finally:
                    await db.close()

                job["processed_files"] += 1

            except Exception as e:
                logger.error("Error analyzing %s: %s", filepath, e)
                job["error_files"] += 1
                job["processed_files"] += 1

        job["status"] = "complete"
        job["current_file"] = None

    except Exception as e:
        logger.error("Scan job %d failed: %s", job_id, e)
        job["status"] = "error"
        job["error_message"] = str(e)

    # Update DB
    db = await get_db()
    try:
        await db.execute(
            """UPDATE scan_jobs SET status=?, total_files=?, processed_files=?,
               skipped_files=?, error_files=?, completed_at=?, error_message=?
               WHERE id=?""",
            (
                job["status"],
                job["total_files"],
                job["processed_files"],
                job["skipped_files"],
                job["error_files"],
                datetime.now(timezone.utc).isoformat(),
                job.get("error_message"),
                job_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()


# --- Library endpoints ---


@app.get("/api/tracks")
async def list_tracks():
    """Get all analyzed tracks."""
    db = await get_db()
    try:
        tracks = await get_all_tracks(db)
        return {"tracks": tracks, "total": len(tracks)}
    finally:
        await db.close()


@app.get("/api/tracks/{track_id}")
async def get_track(track_id: int):
    db = await get_db()
    try:
        track = await get_track_by_id(db, track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        return track
    finally:
        await db.close()


@app.get("/api/stats")
async def library_stats():
    """Get library statistics for dashboard."""
    db = await get_db()
    try:
        tracks = await get_all_tracks(db)
    finally:
        await db.close()

    if not tracks:
        return {"total_tracks": 0}

    bpms = [t["bpm"] for t in tracks if t["bpm"]]
    keys = [t["camelot"] for t in tracks if t["camelot"]]
    genres = [t["genre"] for t in tracks if t["genre"]]
    energies = [t["energy_level"] for t in tracks if t["energy_level"]]
    durations = [t["duration"] for t in tracks if t["duration"]]

    # Camelot distribution
    camelot_dist: dict[str, int] = {}
    for k in keys:
        camelot_dist[k] = camelot_dist.get(k, 0) + 1

    # Genre distribution
    genre_dist: dict[str, int] = {}
    for g in genres:
        genre_dist[g] = genre_dist.get(g, 0) + 1

    # BPM histogram (buckets of 5)
    bpm_hist: dict[str, int] = {}
    for b in bpms:
        bucket = int(b // 5) * 5
        key = f"{bucket}-{bucket+5}"
        bpm_hist[key] = bpm_hist.get(key, 0) + 1

    # Energy distribution
    energy_dist: dict[int, int] = {}
    for e in energies:
        energy_dist[e] = energy_dist.get(e, 0) + 1

    return {
        "total_tracks": len(tracks),
        "total_duration_hours": round(sum(durations) / 3600, 1),
        "avg_bpm": round(sum(bpms) / len(bpms), 1) if bpms else 0,
        "bpm_range": [round(min(bpms), 1), round(max(bpms), 1)] if bpms else [0, 0],
        "camelot_distribution": camelot_dist,
        "genre_distribution": dict(sorted(genre_dist.items(), key=lambda x: -x[1])),
        "bpm_histogram": dict(sorted(bpm_hist.items())),
        "energy_distribution": dict(sorted(energy_dist.items())),
        "formats": list(set(t["format"] for t in tracks if t["format"])),
    }


# --- Theory / Set Planning endpoints ---


@app.post("/api/suggest")
async def suggest_next(req: SuggestRequest):
    """Suggest next tracks based on current track and position in set."""
    db = await get_db()
    try:
        current = await get_track_by_id(db, req.track_id)
        if not current:
            raise HTTPException(status_code=404, detail="Track not found")

        all_tracks = await get_all_tracks(db)
    finally:
        await db.close()

    suggestions = suggest_next_tracks(
        current,
        all_tracks,
        req.position_in_set,
        req.arc_type,
        req.bpm_range,
        set(req.exclude_ids),
        req.limit,
    )

    return {
        "suggestions": [
            {
                "track": track,
                "score": {
                    "harmonic_score": score.harmonic_score,
                    "bpm_score": score.bpm_score,
                    "energy_score": score.energy_score,
                    "overall_score": score.overall_score,
                    "harmonic_move": score.harmonic_move,
                    "bpm_delta": score.bpm_delta,
                    "energy_delta": score.energy_delta,
                    "camelot_distance": score.camelot_distance,
                    "explanation": score.explanation,
                },
            }
            for track, score in suggestions
        ]
    }


@app.post("/api/transition")
async def score_single_transition(req: TransitionRequest):
    """Score a specific transition between two tracks."""
    db = await get_db()
    try:
        track_a = await get_track_by_id(db, req.track_a_id)
        track_b = await get_track_by_id(db, req.track_b_id)
        if not track_a or not track_b:
            raise HTTPException(status_code=404, detail="Track not found")
    finally:
        await db.close()

    score = score_transition(track_a, track_b, req.position_in_set, req.arc_type)

    return {
        "track_a": track_a,
        "track_b": track_b,
        "score": {
            "harmonic_score": score.harmonic_score,
            "bpm_score": score.bpm_score,
            "energy_score": score.energy_score,
            "overall_score": score.overall_score,
            "harmonic_move": score.harmonic_move,
            "bpm_delta": score.bpm_delta,
            "energy_delta": score.energy_delta,
            "camelot_distance": score.camelot_distance,
            "explanation": score.explanation,
        },
    }


@app.post("/api/generate-set")
async def generate_set(req: SetGenerateRequest):
    """Auto-generate a DJ set."""
    db = await get_db()
    try:
        all_tracks = await get_all_tracks(db)
        start_track = None
        if req.start_track_id:
            start_track = await get_track_by_id(db, req.start_track_id)
            if not start_track:
                raise HTTPException(status_code=404, detail="Start track not found")
    finally:
        await db.close()

    if not all_tracks:
        raise HTTPException(status_code=400, detail="No tracks in library. Run a scan first.")

    result = auto_generate_set(
        all_tracks,
        start_track,
        req.target_minutes,
        req.arc_type,
        req.bpm_range,
        req.genre_filter,
    )

    tracks_out = []
    total_duration = 0
    for i, (track, score) in enumerate(result):
        total_duration += track.get("duration", 0)
        tracks_out.append({
            "position": i + 1,
            "track": track,
            "transition": {
                "harmonic_score": score.harmonic_score,
                "bpm_score": score.bpm_score,
                "energy_score": score.energy_score,
                "overall_score": score.overall_score,
                "harmonic_move": score.harmonic_move,
                "bpm_delta": score.bpm_delta,
                "energy_delta": score.energy_delta,
                "explanation": score.explanation,
            } if score else None,
        })

    return {
        "set": tracks_out,
        "total_tracks": len(tracks_out),
        "total_duration_minutes": round(total_duration / 60, 1),
        "arc_type": req.arc_type,
    }


@app.get("/api/arc-types")
async def list_arc_types():
    """List available energy arc types."""
    return {
        "arc_types": [
            {
                "id": "standard",
                "name": "Standard",
                "description": "Classic opener → build → peak → resolution",
            },
            {
                "id": "warmup_peak",
                "name": "Warmup → Peak",
                "description": "Long warmup, sharp peak, quick wind-down",
            },
            {
                "id": "peak_sustain",
                "name": "Peak Sustain",
                "description": "Quick build, sustained high energy, late wind-down",
            },
            {
                "id": "journey",
                "name": "Journey",
                "description": "Multiple peaks and valleys — a dynamic ride",
            },
            {
                "id": "flat",
                "name": "Flat / Chill",
                "description": "Consistent medium energy throughout",
            },
        ]
    }

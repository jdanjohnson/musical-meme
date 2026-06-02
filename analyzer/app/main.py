"""FastAPI backend — serves library data and runs analysis jobs."""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.db import init_db, get_db, upsert_track, get_all_tracks, get_track_by_id, get_tracks_by_ids, get_analyzed_paths
from app.audio import scan_folder, analyze_track, file_hash
from app.theory import (
    score_transition,
    suggest_next_tracks,
    auto_generate_set,
    harmonic_relationship,
    camelot_distance,
    analyze_set_gaps,
)
from app.soundcloud import (
    set_apify_token,
    get_apify_token,
    scrape_soundcloud_url,
    scrape_artist_tracks,
    download_track_ytdlp,
    sc_track_hash,
    parse_sc_track,
    discover_playlist_tracks,
    get_track_metadata,
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
    current_file: Optional[str] = None
    error_message: Optional[str] = None


class SetGenerateRequest(BaseModel):
    start_track_id: Optional[int] = None
    target_minutes: int = 60
    arc_type: str = "standard"
    bpm_range: float = 8.0
    genre_filter: Optional[str] = None


class SuggestRequest(BaseModel):
    track_id: int
    position_in_set: float = 0.5
    arc_type: str = "standard"
    bpm_range: float = 8.0
    exclude_ids: List[int] = []
    limit: int = 20


class TransitionRequest(BaseModel):
    track_a_id: int
    track_b_id: int
    position_in_set: float = 0.5
    arc_type: str = "standard"


class SCConnectRequest(BaseModel):
    apify_token: str


class SCImportRequest(BaseModel):
    soundcloud_url: str
    max_items: int = 500


class SCImportStatus(BaseModel):
    import_id: int
    label: Optional[str] = None
    status: str
    total_tracks: int
    processed_tracks: int
    skipped_tracks: int
    error_tracks: int
    current_track: Optional[str] = None
    error_message: Optional[str] = None


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


@app.delete("/api/tracks/{track_id}")
async def delete_track(track_id: int):
    """Delete a track from the library."""
    db = await get_db()
    try:
        track = await get_track_by_id(db, track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        await db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        await db.commit()
        return {"deleted": True, "id": track_id}
    finally:
        await db.close()


@app.get("/api/tracks/{track_id}/audio")
async def stream_track_audio(track_id: int):
    """Serve audio file for in-browser playback."""
    db = await get_db()
    try:
        track = await get_track_by_id(db, track_id)
    finally:
        await db.close()

    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    file_path = track.get("file_path", "")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    ext = os.path.splitext(file_path)[1].lower()
    media_types = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
                   ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".opus": "audio/opus"}
    media_type = media_types.get(ext, "audio/mpeg")

    return FileResponse(file_path, media_type=media_type, filename=os.path.basename(file_path))


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
            {
                "id": "pride_night",
                "name": "🌈 Pride Night (4hr)",
                "description": "9pm groovy warmup → 10pm build → 11pm peak dance floor → 12am euphoric close",
            },
            {
                "id": "sexy_groovy",
                "name": "Sexy & Groovy",
                "description": "Consistent groove, late peak — keeps it sexy all night",
            },
            {
                "id": "long_build",
                "name": "Long Build (3-5hr)",
                "description": "Very gradual build for marathon sets — slow burn to euphoria",
            },
        ]
    }


# --- Export endpoint ---


@app.post("/api/export-set")
async def export_set(params: dict[str, Any]):
    """Generate a set and return it with SoundCloud URLs for easy finding.

    Same params as generate-set but returns SC links for each track.
    """
    db = await get_db()
    try:
        tracks = await get_all_tracks(db)
    finally:
        await db.close()

    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks in library")

    # Filter to SC tracks if requested
    sc_only = params.get("soundcloud_only", False)
    if sc_only:
        tracks = [t for t in tracks if t.get("soundcloud_url")]

    genre_filter = params.get("genre_filter")
    if genre_filter:
        tracks = [t for t in tracks if t.get("genre", "").lower() == genre_filter.lower()]

    if not tracks:
        raise HTTPException(status_code=400, detail="No matching tracks found")

    start_id = params.get("start_track_id")
    target = params.get("target_minutes", 60)
    arc = params.get("arc_type", "standard")
    bpm_range = params.get("bpm_range", 8)

    set_tracks = auto_generate_set(tracks, start_id, target, arc, bpm_range)

    result = []
    for st in set_tracks:
        entry = {
            "position": st["position"],
            "title": st["track"]["title"],
            "artist": st["track"]["artist"],
            "bpm": st["track"]["bpm"],
            "key": st["track"]["camelot"],
            "energy": st["track"]["energy_level"],
            "genre": st["track"].get("genre", ""),
            "soundcloud_url": st["track"].get("soundcloud_url", ""),
            "transition": st.get("transition_notes", ""),
        }
        if st["track"].get("soundcloud_tags"):
            try:
                entry["tags"] = json.loads(st["track"]["soundcloud_tags"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(entry)

    return {
        "set": result,
        "total_tracks": len(result),
        "total_duration_minutes": sum(
            (st["track"].get("duration") or 0) / 60 for st in set_tracks
        ),
        "arc_type": arc,
    }


@app.post("/api/export-set-folder")
async def export_set_folder(params: dict[str, Any]):
    """Copy set tracks into a numbered folder ready for Rekordbox import."""
    import shutil

    track_ids = params.get("track_ids", [])
    export_name = params.get("name", "DJ Set")

    if not track_ids:
        raise HTTPException(status_code=400, detail="No track IDs provided")

    db = await get_db()
    try:
        tracks = await get_tracks_by_ids(db, track_ids)
    finally:
        await db.close()

    # Build ordered lookup
    id_to_track = {t["id"]: t for t in tracks}
    ordered = [id_to_track[tid] for tid in track_ids if tid in id_to_track]

    if not ordered:
        raise HTTPException(status_code=400, detail="No valid tracks found")

    # Create export folder on desktop or home
    home = os.path.expanduser("~")
    export_dir = os.path.join(home, "DJ Sets", export_name)
    os.makedirs(export_dir, exist_ok=True)

    copied = []
    for i, track in enumerate(ordered, 1):
        src = track.get("file_path", "")
        if not src or not os.path.isfile(src):
            continue

        ext = os.path.splitext(src)[1]
        title = track.get("title") or track.get("filename", "Unknown")
        # Sanitize filename
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_().").strip()
        bpm = track.get("bpm", 0)
        key = track.get("camelot", "")
        dest_name = f"{i:02d} - {safe_title} ({bpm:.0f} BPM, {key}){ext}"
        dest = os.path.join(export_dir, dest_name)

        shutil.copy2(src, dest)
        copied.append({"position": i, "filename": dest_name, "title": title})

    return {
        "export_path": export_dir,
        "tracks_copied": len(copied),
        "tracks": copied,
    }


@app.post("/api/analyze-gaps")
async def analyze_gaps(params: dict[str, Any]):
    """Analyze a generated set for energy, harmonic, and BPM gaps.

    Returns suggestions for what tracks to find to fill holes in the vibe.
    """
    db = await get_db()
    try:
        tracks = await get_all_tracks(db)
    finally:
        await db.close()

    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks in library")

    arc = params.get("arc_type", "standard")
    target = params.get("target_minutes", 60)
    bpm_range = params.get("bpm_range", 8)

    set_result = auto_generate_set(tracks, None, target, arc, bpm_range)
    set_track_dicts = [t for t, _ in set_result]

    gaps = analyze_set_gaps(set_track_dicts, arc, target)

    return {
        "gaps": gaps,
        "total_gaps": len(gaps),
        "high_severity": len([g for g in gaps if g["severity"] == "high"]),
        "set_tracks": len(set_track_dicts),
        "set_duration_minutes": sum(t.get("duration", 300) for t in set_track_dicts) / 60,
    }


# --- SoundCloud endpoints (via Apify) ---

# Track active SC imports
active_sc_imports: dict[int, dict] = {}


@app.post("/api/soundcloud/connect")
async def soundcloud_connect(req: SCConnectRequest):
    """Configure Apify token for SoundCloud scraping."""
    set_apify_token(req.apify_token)
    # Quick validation — try to instantiate client
    try:
        from apify_client import ApifyClient
        client = ApifyClient(req.apify_token)
        user_info = client.user().get()
        username = getattr(user_info, "username", None) or (user_info.get("username") if isinstance(user_info, dict) else "unknown")
        return {"status": "connected", "message": f"Connected as {username}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/soundcloud/status")
async def soundcloud_status():
    """Check if Apify is connected for SoundCloud scraping."""
    token = get_apify_token()
    if not token:
        return {"connected": False}
    try:
        from apify_client import ApifyClient
        client = ApifyClient(token)
        user_info = client.user().get()
        username = getattr(user_info, "username", None) or (user_info.get("username") if isinstance(user_info, dict) else "")
        return {"connected": True, "username": username}
    except Exception:
        return {"connected": False, "error": "Invalid Apify token"}


@app.post("/api/soundcloud/import", response_model=SCImportStatus)
async def soundcloud_import(req: SCImportRequest, background_tasks: BackgroundTasks):
    """Import tracks from a SoundCloud URL — scrapes via Apify, downloads, and analyzes in background.

    Accepts any SoundCloud URL: profile, playlist, or individual track.
    The Apify actor resolves it and returns all tracks found.
    """
    token = get_apify_token()
    if not token:
        raise HTTPException(status_code=400, detail="Apify not connected. Call /api/soundcloud/connect first.")

    # Normalize mobile URLs to desktop
    sc_url = req.soundcloud_url.replace("https://m.soundcloud.com", "https://soundcloud.com")
    label = sc_url

    # Create import job
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO soundcloud_imports (playlist_url, playlist_title, status, started_at) VALUES (?, ?, ?, ?)",
            (sc_url, label, "scraping", datetime.now(timezone.utc).isoformat()),
        )
        import_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    active_sc_imports[import_id] = {
        "label": label,
        "status": "scraping",
        "total_tracks": 0,
        "processed_tracks": 0,
        "skipped_tracks": 0,
        "error_tracks": 0,
        "current_track": None,
    }

    background_tasks.add_task(run_sc_import, import_id, sc_url, req.max_items)

    return SCImportStatus(
        import_id=import_id,
        label=label,
        status="scraping",
        total_tracks=0,
        processed_tracks=0,
        skipped_tracks=0,
        error_tracks=0,
    )


@app.get("/api/soundcloud/import/{import_id}", response_model=SCImportStatus)
async def get_sc_import_status(import_id: int):
    """Get status of a SoundCloud import job."""
    if import_id in active_sc_imports:
        job = active_sc_imports[import_id]
        return SCImportStatus(import_id=import_id, **job)

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM soundcloud_imports WHERE id = ?", (import_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Import job not found")
        return SCImportStatus(
            import_id=row["id"],
            label=row["playlist_title"],
            status=row["status"],
            total_tracks=row["total_tracks"],
            processed_tracks=row["processed_tracks"],
            skipped_tracks=row["skipped_tracks"],
            error_tracks=row["error_tracks"],
            current_track=row["current_track"],
            error_message=row["error_message"],
        )
    finally:
        await db.close()


@app.get("/api/soundcloud/imports")
async def list_sc_imports():
    """List all SoundCloud import jobs."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM soundcloud_imports ORDER BY id DESC")
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            rid = row["id"]
            if rid in active_sc_imports:
                job = active_sc_imports[rid]
                results.append({"import_id": rid, **job})
            else:
                results.append({
                    "import_id": rid,
                    "label": row["playlist_title"],
                    "status": row["status"],
                    "total_tracks": row["total_tracks"],
                    "processed_tracks": row["processed_tracks"],
                    "skipped_tracks": row["skipped_tracks"],
                    "error_tracks": row["error_tracks"],
                    "current_track": row["current_track"],
                    "error_message": row["error_message"],
                })
        return {"imports": results}
    finally:
        await db.close()


async def run_sc_import(import_id: int, soundcloud_url: str, max_items: int) -> None:
    """Background task: discover tracks via yt-dlp, download, analyze each."""
    job = active_sc_imports[import_id]
    job["status"] = "scraping"

    try:
        loop = asyncio.get_event_loop()

        # Step 1: Discover all tracks in playlist via yt-dlp (handles SC pagination)
        discovered = await loop.run_in_executor(None, discover_playlist_tracks, soundcloud_url)

        job["total_tracks"] = len(discovered)
        job["status"] = "analyzing"
        logger.info("SC import %d: yt-dlp discovered %d tracks from %s", import_id, len(discovered), soundcloud_url)

        # Check which SC tracks are already in DB
        db = await get_db()
        try:
            analyzed = await get_analyzed_paths(db)
        finally:
            await db.close()

        for disc in discovered:
            track_url = disc["url"]
            track_id = disc["track_id"]
            if not track_id:
                job["error_tracks"] += 1
                job["processed_tracks"] += 1
                continue

            fake_path = f"soundcloud://{track_id}"
            expected_hash = sc_track_hash(track_id)

            # Skip if already analyzed
            if fake_path in analyzed and analyzed[fake_path] == expected_hash:
                job["skipped_tracks"] += 1
                job["processed_tracks"] += 1
                continue

            job["current_track"] = disc.get("title") or f"Track {track_id}"

            try:
                # Step 2: Get metadata via yt-dlp (title, artist, genre, tags)
                meta = await loop.run_in_executor(None, get_track_metadata, track_url)
                if not meta:
                    meta = {"track_id": track_id, "url": track_url, "title": disc.get("title", "")}

                # Use the resolved URL if available
                resolved_url = meta.get("url") or track_url
                resolved_id = meta.get("track_id") or track_id

                # Update job display with real title
                if meta.get("title"):
                    job["current_track"] = meta["title"]

                # Step 3: Download audio via yt-dlp
                local_path = await loop.run_in_executor(
                    None, download_track_ytdlp, resolved_url, resolved_id, meta.get("title", "")
                )
                if not local_path:
                    job["skipped_tracks"] += 1
                    job["processed_tracks"] += 1
                    continue

                # Step 4: Analyze with librosa
                result = await loop.run_in_executor(None, analyze_track, local_path, None)

                # Override with SC metadata
                track_data = result.to_dict()
                track_data["file_path"] = fake_path
                track_data["file_hash"] = expected_hash
                track_data["title"] = meta.get("title") or track_data.get("title")
                track_data["artist"] = meta.get("artist") or track_data.get("artist")
                track_data["genre"] = meta.get("genre") or track_data.get("genre") or "SoundCloud"
                track_data["folder"] = "SoundCloud"
                track_data["filename"] = f"{meta.get('title', f'sc_{track_id}')}.mp3"
                track_data["soundcloud_url"] = resolved_url
                if meta.get("tags"):
                    track_data["soundcloud_tags"] = json.dumps(meta["tags"])

                db = await get_db()
                try:
                    await upsert_track(db, track_data)
                finally:
                    await db.close()

                job["processed_tracks"] += 1

            except Exception as e:
                logger.error("Error processing SC track %s: %s", track_id, e)
                job["error_tracks"] += 1
                job["processed_tracks"] += 1

        job["status"] = "complete"
        job["current_track"] = None

    except Exception as e:
        logger.error("SC import %d failed: %s", import_id, e)
        job["status"] = "error"
        job["error_message"] = str(e)

    # Update DB
    db = await get_db()
    try:
        await db.execute(
            """UPDATE soundcloud_imports SET status=?, total_tracks=?, processed_tracks=?,
               skipped_tracks=?, error_tracks=?, completed_at=?, error_message=?, current_track=?
               WHERE id=?""",
            (
                job["status"],
                job["total_tracks"],
                job["processed_tracks"],
                job["skipped_tracks"],
                job["error_tracks"],
                datetime.now(timezone.utc).isoformat(),
                job.get("error_message"),
                None,
                import_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()

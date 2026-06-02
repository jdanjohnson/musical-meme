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
from app.soundcloud import (
    set_credentials as sc_set_credentials,
    get_credentials as sc_get_credentials,
    resolve_url,
    get_user_playlists,
    get_playlist_tracks,
    download_track,
    sc_track_hash,
    parse_sc_track_metadata,
    authenticate as sc_authenticate,
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


class SCConnectRequest(BaseModel):
    client_id: str
    client_secret: str


class SCImportRequest(BaseModel):
    playlist_url: str | None = None
    playlist_id: int | None = None
    user_url: str | None = None


class SCImportStatus(BaseModel):
    import_id: int
    playlist_title: str | None = None
    status: str
    total_tracks: int
    processed_tracks: int
    skipped_tracks: int
    error_tracks: int
    current_track: str | None = None
    error_message: str | None = None


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


# --- SoundCloud endpoints ---

# Track active SC imports
active_sc_imports: dict[int, dict] = {}


@app.post("/api/soundcloud/connect")
async def soundcloud_connect(req: SCConnectRequest):
    """Configure SoundCloud API credentials."""
    sc_set_credentials(req.client_id, req.client_secret)
    try:
        await sc_authenticate()
        return {"status": "connected", "message": "SoundCloud authenticated successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/soundcloud/status")
async def soundcloud_status():
    """Check if SoundCloud is connected."""
    creds = sc_get_credentials()
    if not creds:
        return {"connected": False}
    try:
        await sc_authenticate()
        return {"connected": True, "client_id": creds.client_id[:8] + "..."}
    except Exception:
        return {"connected": False, "error": "Authentication failed"}


@app.get("/api/soundcloud/playlists")
async def soundcloud_playlists(user_url: str):
    """Get playlists for a SoundCloud user URL."""
    creds = sc_get_credentials()
    if not creds:
        raise HTTPException(status_code=400, detail="SoundCloud not connected. Call /api/soundcloud/connect first.")

    try:
        playlists = await get_user_playlists(user_url)
        return {
            "playlists": [
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "track_count": p.get("track_count", len(p.get("tracks", []))),
                    "duration_ms": p.get("duration", 0),
                    "permalink_url": p.get("permalink_url"),
                    "artwork_url": p.get("artwork_url"),
                    "created_at": p.get("created_at"),
                }
                for p in playlists
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/soundcloud/import", response_model=SCImportStatus)
async def soundcloud_import(req: SCImportRequest, background_tasks: BackgroundTasks):
    """Import tracks from a SoundCloud playlist — downloads and analyzes in background."""
    creds = sc_get_credentials()
    if not creds:
        raise HTTPException(status_code=400, detail="SoundCloud not connected")

    # Resolve the playlist
    playlist_id = req.playlist_id
    playlist_title = None
    playlist_url = req.playlist_url

    if req.playlist_url and not req.playlist_id:
        try:
            resolved = await resolve_url(req.playlist_url)
            playlist_id = resolved.get("id")
            playlist_title = resolved.get("title")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cannot resolve URL: {e}")
    elif req.user_url:
        # Import ALL playlists for a user
        try:
            playlists = await get_user_playlists(req.user_url)
            # Start an import for each playlist
            import_ids = []
            for p in playlists:
                pid = p.get("id")
                ptitle = p.get("title")
                db = await get_db()
                try:
                    cursor = await db.execute(
                        "INSERT INTO soundcloud_imports (playlist_id, playlist_title, playlist_url, status, started_at) VALUES (?, ?, ?, ?, ?)",
                        (pid, ptitle, p.get("permalink_url"), "pending", datetime.now(timezone.utc).isoformat()),
                    )
                    import_id = cursor.lastrowid
                    await db.commit()
                finally:
                    await db.close()

                active_sc_imports[import_id] = {
                    "playlist_title": ptitle,
                    "status": "pending",
                    "total_tracks": 0,
                    "processed_tracks": 0,
                    "skipped_tracks": 0,
                    "error_tracks": 0,
                    "current_track": None,
                }
                background_tasks.add_task(run_sc_import, import_id, pid, ptitle)
                import_ids.append(import_id)

            return SCImportStatus(
                import_id=import_ids[0] if import_ids else 0,
                playlist_title=f"All playlists ({len(import_ids)})",
                status="importing",
                total_tracks=0,
                processed_tracks=0,
                skipped_tracks=0,
                error_tracks=0,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    if not playlist_id:
        raise HTTPException(status_code=400, detail="Provide playlist_url, playlist_id, or user_url")

    # Create import job
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO soundcloud_imports (playlist_id, playlist_title, playlist_url, status, started_at) VALUES (?, ?, ?, ?, ?)",
            (playlist_id, playlist_title, playlist_url, "importing", datetime.now(timezone.utc).isoformat()),
        )
        import_id = cursor.lastrowid
        await db.commit()
    finally:
        await db.close()

    active_sc_imports[import_id] = {
        "playlist_title": playlist_title,
        "status": "importing",
        "total_tracks": 0,
        "processed_tracks": 0,
        "skipped_tracks": 0,
        "error_tracks": 0,
        "current_track": None,
    }

    background_tasks.add_task(run_sc_import, import_id, playlist_id, playlist_title)

    return SCImportStatus(
        import_id=import_id,
        playlist_title=playlist_title,
        status="importing",
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
            playlist_title=row["playlist_title"],
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
                    "playlist_title": row["playlist_title"],
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


async def run_sc_import(import_id: int, playlist_id: int, playlist_title: str | None) -> None:
    """Background task: download + analyze all tracks from a SoundCloud playlist."""
    job = active_sc_imports[import_id]
    job["status"] = "fetching"

    try:
        # Get playlist tracks
        sc_tracks = await get_playlist_tracks(playlist_id)
        job["total_tracks"] = len(sc_tracks)
        job["status"] = "importing"
        logger.info("SC import %d: %d tracks from '%s'", import_id, len(sc_tracks), playlist_title)

        # Check which SC tracks are already in DB
        db = await get_db()
        try:
            analyzed = await get_analyzed_paths(db)
        finally:
            await db.close()

        for sc_track in sc_tracks:
            meta = parse_sc_track_metadata(sc_track)
            sc_id = meta["sc_id"]
            if not sc_id:
                job["error_tracks"] += 1
                job["processed_tracks"] += 1
                continue

            fake_path = f"soundcloud://{sc_id}"
            expected_hash = sc_track_hash(sc_id)

            # Skip if already analyzed
            if fake_path in analyzed and analyzed[fake_path] == expected_hash:
                job["skipped_tracks"] += 1
                job["processed_tracks"] += 1
                continue

            job["current_track"] = meta.get("title", f"Track {sc_id}")

            if not meta.get("streamable", False):
                logger.warning("SC track %d not streamable, skipping", sc_id)
                job["skipped_tracks"] += 1
                job["processed_tracks"] += 1
                continue

            try:
                # Download
                local_path = await download_track(sc_id, meta.get("title", ""))
                if not local_path:
                    job["error_tracks"] += 1
                    job["processed_tracks"] += 1
                    continue

                # Analyze in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, analyze_track, local_path, None)

                # Override with SC metadata + use fake path for dedup
                track_data = result.to_dict()
                track_data["file_path"] = fake_path
                track_data["file_hash"] = expected_hash
                track_data["title"] = meta.get("title") or track_data.get("title")
                track_data["artist"] = meta.get("artist") or track_data.get("artist")
                if meta.get("genre"):
                    track_data["genre"] = meta["genre"]
                track_data["folder"] = f"SoundCloud/{playlist_title or 'Imported'}"
                track_data["filename"] = f"{meta.get('title', f'sc_{sc_id}')}.mp3"

                db = await get_db()
                try:
                    await upsert_track(db, track_data)
                finally:
                    await db.close()

                job["processed_tracks"] += 1

            except Exception as e:
                logger.error("Error processing SC track %d: %s", sc_id, e)
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

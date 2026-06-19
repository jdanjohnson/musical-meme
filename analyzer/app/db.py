"""SQLite database for caching audio analysis results."""
from __future__ import annotations

import aiosqlite
import json
import os
from pathlib import Path

DB_PATH = os.environ.get("DJ_PLANNER_DB", str(Path.home() / ".dj-set-planner" / "library.db"))


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                filename TEXT NOT NULL,
                folder TEXT NOT NULL,
                genre TEXT,

                -- audio analysis
                duration REAL,
                bpm REAL,
                bpm_confidence REAL,
                key TEXT,
                key_confidence REAL,
                camelot TEXT,
                energy REAL,
                loudness REAL,
                spectral_centroid REAL,

                -- metadata
                title TEXT,
                artist TEXT,
                album TEXT,
                year INTEGER,
                format TEXT,
                sample_rate INTEGER,
                channels INTEGER,
                bitrate INTEGER,

                -- computed
                energy_level INTEGER,  -- 1-10 scale
                brightness REAL,       -- 0-1 scale

                -- timestamps
                analyzed_at TEXT NOT NULL,
                file_modified_at TEXT NOT NULL,

                -- soundcloud
                soundcloud_url TEXT,
                soundcloud_tags TEXT,  -- JSON array

                -- user overrides
                user_bpm REAL,
                user_key TEXT,
                user_energy INTEGER,
                user_genre TEXT,
                user_rating INTEGER,
                user_tags TEXT,  -- JSON array
                user_notes TEXT
            );

            CREATE TABLE IF NOT EXISTS soundcloud_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER,
                playlist_title TEXT,
                playlist_url TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                total_tracks INTEGER DEFAULT 0,
                processed_tracks INTEGER DEFAULT 0,
                skipped_tracks INTEGER DEFAULT 0,
                error_tracks INTEGER DEFAULT 0,
                current_track TEXT,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tracks_camelot ON tracks(camelot);
            CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm);
            CREATE INDEX IF NOT EXISTS idx_tracks_energy ON tracks(energy_level);
            CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
            CREATE INDEX IF NOT EXISTS idx_tracks_folder ON tracks(folder);

            CREATE TABLE IF NOT EXISTS sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                target_duration INTEGER,  -- minutes
                energy_arc TEXT,          -- JSON: array of {position, energy}
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS set_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                set_id INTEGER NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
                track_id INTEGER NOT NULL REFERENCES tracks(id),
                position INTEGER NOT NULL,
                transition_score REAL,
                transition_notes TEXT,
                UNIQUE(set_id, position)
            );

            CREATE TABLE IF NOT EXISTS scan_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',  -- pending, scanning, analyzing, complete, error
                total_files INTEGER DEFAULT 0,
                processed_files INTEGER DEFAULT 0,
                skipped_files INTEGER DEFAULT 0,
                error_files INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS deleted_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                filename TEXT,
                deleted_at TEXT NOT NULL
            );
        """)
        # Migrations — add columns if missing (each individually for robustness)
        migration_columns = [
            ("soundcloud_url", "TEXT"),
            ("soundcloud_tags", "TEXT"),
            ("has_vocals", "INTEGER DEFAULT 0"),
            ("vocal_confidence", "REAL DEFAULT 0"),
            ("intro_end_sec", "REAL DEFAULT 0"),
            ("outro_start_sec", "REAL DEFAULT 0"),
            ("phrase_length_sec", "REAL DEFAULT 0"),
            ("ai_genre", "TEXT"),
            ("ai_genre_confidence", "REAL DEFAULT 0"),
            ("mood_primary", "TEXT"),
            ("mood_valence", "REAL DEFAULT 0"),
            ("mood_arousal", "REAL DEFAULT 0"),
            ("mood_tension", "REAL DEFAULT 0"),
            ("mood_warmth", "REAL DEFAULT 0"),
            ("mood_tags", "TEXT"),
            ("audio_embedding", "TEXT"),
            ("structure_drops", "TEXT"),
            ("structure_breakdowns", "TEXT"),
            ("structure_builds", "TEXT"),
        ]
        for col_name, col_type in migration_columns:
            try:
                await db.execute(f"SELECT {col_name} FROM tracks LIMIT 1")
            except Exception:
                await db.execute(f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type}")
        await db.commit()
    finally:
        await db.close()


async def upsert_track(db: aiosqlite.Connection, track_data: dict) -> int:
    columns = list(track_data.keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_str = ", ".join(columns)
    update_str = ", ".join([f"{c} = excluded.{c}" for c in columns if c != "file_path"])

    sql = f"""
        INSERT INTO tracks ({col_str}) VALUES ({placeholders})
        ON CONFLICT(file_path) DO UPDATE SET {update_str}
    """
    cursor = await db.execute(sql, list(track_data.values()))
    await db.commit()
    return cursor.lastrowid


async def get_all_tracks(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute("SELECT * FROM tracks ORDER BY folder, filename")
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_track_by_id(db: aiosqlite.Connection, track_id: int) -> dict | None:
    cursor = await db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_tracks_by_ids(db: aiosqlite.Connection, track_ids: list[int]) -> list[dict]:
    if not track_ids:
        return []
    placeholders = ",".join(["?"] * len(track_ids))
    cursor = await db.execute(
        f"SELECT * FROM tracks WHERE id IN ({placeholders})", track_ids
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_analyzed_paths(db: aiosqlite.Connection) -> dict[str, str]:
    """Return {file_path: file_hash} for all analyzed tracks."""
    cursor = await db.execute("SELECT file_path, file_hash FROM tracks")
    rows = await cursor.fetchall()
    return {row["file_path"]: row["file_hash"] for row in rows}


async def add_to_skip_list(db: aiosqlite.Connection, file_path: str, filename: str) -> None:
    """Record a deleted track so it won't be re-analyzed on future scans."""
    from datetime import datetime, timezone
    await db.execute(
        "INSERT OR IGNORE INTO deleted_tracks (file_path, filename, deleted_at) VALUES (?, ?, ?)",
        (file_path, filename, datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()


async def get_skip_list(db: aiosqlite.Connection) -> set[str]:
    """Return set of file paths that should be skipped during scans."""
    cursor = await db.execute("SELECT file_path FROM deleted_tracks")
    rows = await cursor.fetchall()
    return {row["file_path"] for row in rows}

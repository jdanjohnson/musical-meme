"""SoundCloud integration — yt-dlp for playlist discovery & download, Apify as optional metadata enrichment."""

import hashlib
import json
import logging
import os
import re
import subprocess
from pathlib import Path

from apify_client import ApifyClient

logger = logging.getLogger(__name__)

APIFY_ACTOR = "crawlergang/soundcloud-scraper"
DOWNLOAD_DIR = os.path.join(str(Path.home()), ".dj-set-planner", "soundcloud-cache")

# Module-level Apify token store
_apify_token: str | None = None


def set_apify_token(token: str) -> None:
    global _apify_token
    _apify_token = token


def get_apify_token() -> str | None:
    return _apify_token


def _get_client() -> ApifyClient:
    token = get_apify_token()
    if not token:
        raise ValueError("Apify token not configured")
    return ApifyClient(token)


# ---------------------------------------------------------------------------
# yt-dlp–based playlist/track discovery (handles SC pagination correctly)
# ---------------------------------------------------------------------------


def discover_playlist_tracks(sc_url: str) -> list[dict]:
    """Use yt-dlp --flat-playlist to discover ALL tracks in a SC playlist/set.

    Returns list of dicts with url, title (may be None), track_id.
    This handles SC's API pagination correctly — Apify's actor misses tracks.
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-J", sc_url],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("yt-dlp flat-playlist failed: %s", result.stderr[:200])
            return []

        data = json.loads(result.stdout)

        # Single track URL (not a playlist)
        if data.get("_type") != "playlist":
            return [{
                "url": data.get("webpage_url") or data.get("url") or sc_url,
                "title": data.get("title"),
                "track_id": _extract_track_id(data.get("webpage_url") or sc_url),
            }]

        entries = data.get("entries", [])
        tracks = []
        for entry in entries:
            url = entry.get("url", "")
            # Some entries are api-v2 URLs, convert to proper SC URLs
            if "api-v2.soundcloud.com/tracks/" in url:
                # We'll resolve these during download
                track_id = url.split("/tracks/")[-1].split("?")[0]
            else:
                track_id = _extract_track_id(url)
            tracks.append({
                "url": url,
                "title": entry.get("title"),
                "track_id": track_id or hashlib.md5(url.encode()).hexdigest()[:12],
            })

        logger.info("yt-dlp discovered %d tracks in playlist: %s", len(tracks), sc_url)
        return tracks

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp playlist discovery timed out for: %s", sc_url)
        return []
    except (json.JSONDecodeError, Exception) as e:
        logger.error("yt-dlp playlist discovery failed: %s", e)
        return []


def get_track_metadata(sc_url: str) -> dict:
    """Use yt-dlp to get full metadata for a single track without downloading.

    Returns dict with title, artist, genre, duration, url, etc.
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-download", "-J", "--no-playlist", sc_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        url = data.get("webpage_url") or data.get("url") or sc_url

        return {
            "track_id": _extract_track_id(url) or data.get("id", ""),
            "title": data.get("title", ""),
            "artist": data.get("uploader", "") or data.get("artist", ""),
            "url": url,
            "genre": data.get("genre"),
            "tags": data.get("tags") or [],
            "duration_sec": data.get("duration") or 0,
            "thumbnail": data.get("thumbnail", ""),
            "view_count": data.get("view_count", 0),
            "like_count": data.get("like_count", 0),
        }

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to get metadata for %s: %s", sc_url, e)
        return {}


def _extract_track_id(url: str) -> str:
    """Extract a stable ID from a SoundCloud URL."""
    if not url:
        return ""
    # api-v2 URL: https://api-v2.soundcloud.com/tracks/2169230112
    if "api-v2.soundcloud.com/tracks/" in url:
        return url.split("/tracks/")[-1].split("?")[0]
    # Regular URL: https://soundcloud.com/artist/track-slug
    parts = url.replace("https://soundcloud.com/", "").strip("/").split("/")
    if len(parts) >= 2 and parts[0] != "":
        return f"{parts[0]}_{parts[-1]}"
    return hashlib.md5(url.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Apify-based scraping (kept as fallback / metadata enrichment)
# ---------------------------------------------------------------------------


def scrape_soundcloud_url(urls: list[str], max_items: int = 500) -> list[dict]:
    """Scrape tracks from SoundCloud URLs via Apify (fallback for metadata)."""
    client = _get_client()
    run_input = {
        "mode": "byUrl",
        "startUrls": [{"url": u} for u in urls],
        "maxItems": max_items,
    }
    logger.info("Starting Apify run for %d URLs (max %d items)", len(urls), max_items)
    run = client.actor(APIFY_ACTOR).call(run_input=run_input)

    dataset_id = run.default_dataset_id
    items = list(client.dataset(dataset_id).iterate_items())
    tracks = [item for item in items if item.get("recordType") == "track"]
    logger.info("Apify returned %d items, %d tracks", len(items), len(tracks))
    return tracks


def scrape_artist_tracks(artist_url: str, max_items: int = 500) -> list[dict]:
    """Get all tracks from an artist profile."""
    client = _get_client()
    run_input = {
        "mode": "artistTracks",
        "artistUrl": artist_url,
        "maxItems": max_items,
    }
    logger.info("Fetching artist tracks: %s", artist_url)
    run = client.actor(APIFY_ACTOR).call(run_input=run_input)

    dataset_id = run.default_dataset_id
    items = list(client.dataset(dataset_id).iterate_items())
    tracks = [item for item in items if item.get("trackId")]
    logger.info("Artist tracks: %d items, %d tracks", len(items), len(tracks))
    return tracks


# ---------------------------------------------------------------------------
# Track download
# ---------------------------------------------------------------------------


def download_track_ytdlp(sc_url: str, track_id: str, title: str = "track") -> str | None:
    """Download a SoundCloud track via yt-dlp. Returns local file path or None."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(track_id))
    cache_path = os.path.join(DOWNLOAD_DIR, f"sc_{safe_id}.mp3")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
        logger.info("SC track %s already cached: %s", track_id, cache_path)
        return cache_path

    if not sc_url:
        logger.warning("No SoundCloud URL for track %s (%s)", track_id, title)
        return None

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", cache_path.replace(".mp3", ".%(ext)s"),
                "--no-playlist",
                "--quiet",
                sc_url,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
            logger.info("Downloaded SC track %s → %s", track_id, cache_path)
            return cache_path

        for ext in [".mp3", ".opus", ".m4a", ".ogg", ".wav"]:
            alt_path = cache_path.replace(".mp3", ext)
            if os.path.exists(alt_path) and os.path.getsize(alt_path) > 1000:
                logger.info("Downloaded SC track %s → %s", track_id, alt_path)
                return alt_path

        logger.warning(
            "yt-dlp failed for track %s (%s): %s",
            track_id, title, result.stderr[:200] if result.stderr else "no output"
        )
        return None

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp timed out for track %s", track_id)
        return None
    except Exception as e:
        logger.error("Failed to download SC track %s: %s", track_id, e)
        return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def sc_track_hash(track_id: str) -> str:
    """Generate a stable hash for a SoundCloud track."""
    return hashlib.md5(f"soundcloud:{track_id}".encode()).hexdigest()


def parse_sc_track(sc_item: dict) -> dict:
    """Extract useful metadata from an Apify SoundCloud scrape result."""
    return {
        "track_id": sc_item.get("trackId", ""),
        "title": sc_item.get("title", ""),
        "artist": sc_item.get("artist", ""),
        "url": sc_item.get("url", ""),
        "genre": sc_item.get("genre"),
        "tags": sc_item.get("tags", []),
        "duration_str": sc_item.get("duration", ""),
        "duration_sec": _parse_duration_str(sc_item.get("duration")),
        "stream_url": sc_item.get("streamUrl", ""),
        "artwork_url": sc_item.get("artworkUrl", ""),
        "play_count": sc_item.get("playCount", 0),
        "like_count": sc_item.get("likeCount", 0),
    }


def _parse_duration_str(dur_str: str | None) -> float:
    """Parse duration string like '3:45' or '1:02:30' to seconds."""
    if not dur_str:
        return 0.0
    parts = dur_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        else:
            return float(parts[0])
    except (ValueError, IndexError):
        return 0.0

"""SoundCloud integration via Apify — scrape playlists, download tracks, run analysis."""

import hashlib
import logging
import os
import re
from pathlib import Path

import httpx
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


def scrape_soundcloud_url(urls: list[str], max_items: int = 500) -> list[dict]:
    """Scrape tracks from SoundCloud URLs (playlists, profiles, individual tracks).

    Uses the crawlergang/soundcloud-scraper Apify actor in byUrl mode.
    Returns list of track dicts with title, artist, genre, streamUrl, etc.
    """
    client = _get_client()
    run_input = {
        "mode": "byUrl",
        "startUrls": [{"url": u} for u in urls],
        "maxItems": max_items,
    }
    logger.info("Starting Apify run for %d URLs (max %d items)", len(urls), max_items)
    run = client.actor(APIFY_ACTOR).call(run_input=run_input)

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    # Filter to only tracks (not users/playlists metadata)
    tracks = [item for item in items if item.get("recordType") == "track" or item.get("trackId")]
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

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    tracks = [item for item in items if item.get("trackId")]
    logger.info("Artist tracks: %d items, %d tracks", len(items), len(tracks))
    return tracks


async def download_stream(stream_url: str, track_id: str, title: str = "track") -> str | None:
    """Download a track's stream URL to local cache. Returns local file path or None."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(track_id))
    cache_path = os.path.join(DOWNLOAD_DIR, f"sc_{safe_id}.mp3")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
        logger.info("SC track %s already cached: %s", track_id, cache_path)
        return cache_path

    if not stream_url:
        logger.warning("No stream URL for track %s (%s)", track_id, title)
        return None

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            resp = await client.get(stream_url)
            if resp.status_code != 200:
                logger.warning("Cannot download track %s (%s): HTTP %d", track_id, title, resp.status_code)
                return None

            with open(cache_path, "wb") as f:
                f.write(resp.content)

            if os.path.getsize(cache_path) < 1000:
                os.remove(cache_path)
                logger.warning("Downloaded file too small for track %s, likely not audio", track_id)
                return None

            logger.info("Downloaded SC track %s → %s (%d bytes)", track_id, cache_path, len(resp.content))
            return cache_path

    except Exception as e:
        logger.error("Failed to download SC track %s: %s", track_id, e)
        return None


def sc_track_hash(track_id: str) -> str:
    """Generate a stable hash for a SoundCloud track."""
    return hashlib.md5(f"soundcloud:{track_id}".encode()).hexdigest()


def parse_duration_str(dur_str: str | None) -> float:
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
        "duration_sec": parse_duration_str(sc_item.get("duration")),
        "stream_url": sc_item.get("streamUrl", ""),
        "artwork_url": sc_item.get("artworkUrl", ""),
        "play_count": sc_item.get("playCount", 0),
        "like_count": sc_item.get("likeCount", 0),
    }

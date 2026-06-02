"""SoundCloud integration — fetch playlists, download tracks, run analysis."""

import asyncio
import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

SC_API_BASE = "https://api.soundcloud.com"
SC_AUTH_URL = "https://secure.soundcloud.com/oauth/token"

DOWNLOAD_DIR = os.path.join(str(Path.home()), ".dj-set-planner", "soundcloud-cache")


@dataclass
class SCCredentials:
    client_id: str
    client_secret: str
    access_token: str | None = None
    refresh_token: str | None = None


# Module-level credential store (set via API)
_credentials: SCCredentials | None = None


def set_credentials(client_id: str, client_secret: str) -> None:
    global _credentials
    _credentials = SCCredentials(client_id=client_id, client_secret=client_secret)


def get_credentials() -> SCCredentials | None:
    return _credentials


async def authenticate() -> str:
    """Get access token via Client Credentials flow (public resources)."""
    creds = get_credentials()
    if not creds:
        raise ValueError("SoundCloud credentials not configured")

    if creds.access_token:
        return creds.access_token

    import base64
    encoded = base64.b64encode(f"{creds.client_id}:{creds.client_secret}".encode()).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            SC_AUTH_URL,
            headers={
                "Accept": "application/json; charset=utf-8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded}",
            },
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        data = resp.json()

    creds.access_token = data["access_token"]
    creds.refresh_token = data.get("refresh_token")
    return creds.access_token


async def sc_get(path: str, params: dict | None = None) -> dict:
    """Authenticated GET to SoundCloud API."""
    token = await authenticate()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SC_API_BASE}{path}",
            params=params or {},
            headers={"Authorization": f"OAuth {token}"},
            follow_redirects=True,
            timeout=30.0,
        )
        if resp.status_code == 401:
            # Token expired, refresh
            creds = get_credentials()
            if creds:
                creds.access_token = None
            token = await authenticate()
            resp = await client.get(
                f"{SC_API_BASE}{path}",
                params=params or {},
                headers={"Authorization": f"OAuth {token}"},
                follow_redirects=True,
                timeout=30.0,
            )
        resp.raise_for_status()
        return resp.json()


async def resolve_url(url: str) -> dict:
    """Resolve a SoundCloud URL to an API resource."""
    return await sc_get("/resolve", {"url": url})


async def get_user_playlists(user_url: str) -> list[dict]:
    """Get all playlists for a user URL like https://soundcloud.com/username."""
    user = await resolve_url(user_url)
    user_id = user["id"]

    playlists = []
    data = await sc_get(f"/users/{user_id}/playlists", {"linked_partitioning": "true", "limit": 50})
    playlists.extend(data.get("collection", []))

    # Paginate
    while data.get("next_href"):
        token = await authenticate()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                data["next_href"],
                headers={"Authorization": f"OAuth {token}"},
                follow_redirects=True,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        playlists.extend(data.get("collection", []))

    return playlists


async def get_playlist_tracks(playlist_id: int) -> list[dict]:
    """Get all tracks in a playlist."""
    data = await sc_get(f"/playlists/{playlist_id}")
    return data.get("tracks", [])


async def download_track(track_id: int, title: str = "track") -> str | None:
    """Download a track's stream to local cache. Returns local file path or None."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Check cache
    cache_path = os.path.join(DOWNLOAD_DIR, f"sc_{track_id}.mp3")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
        logger.info("SoundCloud track %d already cached: %s", track_id, cache_path)
        return cache_path

    try:
        token = await authenticate()
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            # Get stream URL
            resp = await client.get(
                f"{SC_API_BASE}/tracks/{track_id}/stream",
                headers={"Authorization": f"OAuth {token}"},
            )
            if resp.status_code == 401:
                creds = get_credentials()
                if creds:
                    creds.access_token = None
                token = await authenticate()
                resp = await client.get(
                    f"{SC_API_BASE}/tracks/{track_id}/stream",
                    headers={"Authorization": f"OAuth {token}"},
                    follow_redirects=True,
                )

            if resp.status_code != 200:
                logger.warning("Cannot stream track %d (%s): HTTP %d", track_id, title, resp.status_code)
                return None

            # Write to cache
            with open(cache_path, "wb") as f:
                f.write(resp.content)

            logger.info("Downloaded SC track %d → %s (%d bytes)", track_id, cache_path, len(resp.content))
            return cache_path

    except Exception as e:
        logger.error("Failed to download SC track %d: %s", track_id, e)
        return None


def sc_track_hash(track_id: int) -> str:
    """Generate a stable hash for a SoundCloud track."""
    return hashlib.md5(f"soundcloud:{track_id}".encode()).hexdigest()


def parse_sc_track_metadata(sc_track: dict) -> dict:
    """Extract useful metadata from a SoundCloud track API response."""
    return {
        "sc_id": sc_track.get("id"),
        "title": sc_track.get("title"),
        "artist": sc_track.get("user", {}).get("username"),
        "duration_ms": sc_track.get("duration", 0),
        "genre": sc_track.get("genre") or sc_track.get("tag_list", "").split(" ")[0] or None,
        "permalink_url": sc_track.get("permalink_url"),
        "artwork_url": sc_track.get("artwork_url"),
        "waveform_url": sc_track.get("waveform_url"),
        "streamable": sc_track.get("streamable", False),
        "bpm": sc_track.get("bpm"),
        "key_signature": sc_track.get("key_signature"),
    }

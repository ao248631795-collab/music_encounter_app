import time
import base64
from typing import Optional
import httpx
from app.config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_SEARCH_TIMEOUT_SEC,
)

# メモリキャッシュ（アクセストークンと有効期限）
_token: Optional[str] = None
_token_expires_at: float = 0.0


def _fetch_token() -> tuple:
    credentials = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    resp = httpx.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {credentials}"},
        data={"grant_type": "client_credentials"},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["expires_in"]


def get_token() -> str:
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at - 60:
        return _token
    token, expires_in = _fetch_token()
    _token = token
    _token_expires_at = time.time() + expires_in
    return _token


def search_tracks(query: str, limit: int = 10) -> list[dict]:
    """
    Spotify Search APIで楽曲を検索する。
    失敗時は SpotifySearchError を送出する。
    """
    try:
        token = get_token()
        resp = httpx.get(
            "https://api.spotify.com/v1/search",
            params={"q": query, "type": "track", "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
            timeout=SPOTIFY_SEARCH_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        items = resp.json().get("tracks", {}).get("items", [])
        return [
            {
                "spotify_track_id": t["id"],
                "title": t["name"],
                "artist": ", ".join(a["name"] for a in t["artists"]),
                "album_art_url": (
                    t["album"]["images"][0]["url"] if t["album"]["images"] else None
                ),
            }
            for t in items
        ]
    except Exception as e:
        raise SpotifySearchError(str(e)) from e


class SpotifySearchError(Exception):
    pass

"""
SpotifyユーザーOAuthクライアント（プレイリスト作成用）。

既存の spotify_client.py（Client Credentials・検索専用）とは別物。
こちらは各ユーザー本人のアカウントでプレイリストを作るため、
Authorization Code Flow でユーザーの refresh_token を得て使う。

ネットワーク呼び出しはすべて httpx（導入済み）。
HTTPエラー・タイムアウトは SpotifyUserAuthError に変換して送出する。
"""
import base64
from typing import Optional
from urllib.parse import urlencode
import httpx
from app.config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
)

# ユーザーが本人アカウントに非公開プレイリストを作れる最小スコープ
SPOTIFY_SCOPE = "playlist-modify-private"

_ACCOUNTS_BASE = "https://accounts.spotify.com"
_API_BASE = "https://api.spotify.com/v1"
_TIMEOUT_SEC = 10.0


class SpotifyUserAuthError(Exception):
    """Spotifyユーザー認可・API呼び出しに失敗したときに送出する。"""
    pass


def _to_error(e: Exception) -> "SpotifyUserAuthError":
    """例外をSpotifyUserAuthErrorへ変換。HTTPエラーは応答本文も含めて診断しやすくする。"""
    if isinstance(e, httpx.HTTPStatusError):
        return SpotifyUserAuthError(f"{e} body={e.response.text[:200]}")
    return SpotifyUserAuthError(str(e))


def _basic_auth_header() -> str:
    """client_id:client_secret のBasic認証ヘッダ値を組み立てる。"""
    credentials = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    return f"Basic {credentials}"


def get_authorize_url(state: str) -> str:
    """Spotify認可画面へのURLを組み立てる（ネットワーク呼び出しなし）。"""
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPE,
        "state": state,
        # 同意済みでも必ず確認画面を出す（アカウントの取り違え防止。
        # これがないとSpotifyは無言で前回のアカウントを再認可する）
        "show_dialog": "true",
    }
    return f"{_ACCOUNTS_BASE}/authorize?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """
    認可コードをアクセストークン・リフレッシュトークンに交換する。
    戻り値はSpotifyのトークンレスポンス(dict)そのまま（access_token/refresh_token等）。
    """
    try:
        resp = httpx.post(
            f"{_ACCOUNTS_BASE}/api/token",
            headers={"Authorization": _basic_auth_header()},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
            },
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise _to_error(e) from e


def refresh_access_token(refresh_token: str) -> dict:
    """
    refresh_tokenから新しいaccess_tokenを得る。
    新しいrefresh_tokenが返る場合もあるため、呼び出し元で保存できるようdictごと返す。
    """
    try:
        resp = httpx.post(
            f"{_ACCOUNTS_BASE}/api/token",
            headers={"Authorization": _basic_auth_header()},
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise _to_error(e) from e


def get_me(access_token: str) -> str:
    """現在のユーザーのSpotify user_idを返す。"""
    try:
        resp = httpx.get(
            f"{_API_BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except Exception as e:
        raise _to_error(e) from e


def create_playlist(access_token: str, name: str, description: str) -> dict:
    """
    認可ユーザー本人に非公開(public: false)プレイリストを作成する。
    戻り値: {"id": プレイリストID, "url": external_urls.spotify}

    注意: /users/{user_id}/playlists 形式は開発モードのアプリで
    素の403 Forbiddenを返すケースがあるため（2026-07-06に実環境で確認）、
    /me/playlists 形式を使う。
    """
    try:
        resp = httpx.post(
            f"{_API_BASE}/me/playlists",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "name": name,
                "description": description,
                "public": False,
            },
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "id": data["id"],
            "url": data.get("external_urls", {}).get("spotify", ""),
        }
    except Exception as e:
        raise _to_error(e) from e


def unfollow_playlist(access_token: str, playlist_id: str) -> None:
    """
    プレイリストをライブラリから削除する（Spotifyでは「フォロー解除」が削除に相当）。
    曲追加に失敗した際、空プレイリストを残さないための後片付けに使う。
    """
    try:
        resp = httpx.delete(
            f"{_API_BASE}/playlists/{playlist_id}/followers",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
    except Exception as e:
        raise _to_error(e) from e


def add_tracks(access_token: str, playlist_id: str, track_uris: list) -> None:
    """
    プレイリストにトラックを追加する。
    月間は最大31曲なので1リクエスト（上限100）で足りる。
    """
    try:
        resp = httpx.post(
            f"{_API_BASE}/playlists/{playlist_id}/tracks",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"uris": track_uris},
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
    except Exception as e:
        raise _to_error(e) from e

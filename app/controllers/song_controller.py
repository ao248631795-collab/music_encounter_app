from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user_id
import re
from app.config import SONG_MAX_PER_USER
from app.services import song_service, spotify_client
from app.services.spotify_client import SpotifySearchError
from app.services.song_service import SongDuplicateError, SongLimitError, SongNotFoundError

# SpotifyトラックIDの形式（base62・22文字）。不正値のDB混入とiframe srcへの流入を防ぐ
TRACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{22}$")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/songs")
def list_songs(request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    songs = song_service.get_songs(db, user_id)
    active_song = song_service.get_active_song(db, user_id)
    # POST /songs のエラーはPRGパターンでクエリパラメータ経由で受け取る
    error = {
        "limit": f"プールに保存できる曲は最大{SONG_MAX_PER_USER}曲です。",
        "duplicate": "この曲はすでにプールに登録されています。",
    }.get(request.query_params.get("error"))
    return templates.TemplateResponse("songs/list.html", {
        "request": request,
        "songs": songs,
        "active_song": active_song,
        "error": error,
    })


@router.get("/songs/search")
def search_form(request: Request, q: str = ""):
    results = []
    error = None
    not_found = False

    if q:
        try:
            results = spotify_client.search_tracks(q)
            if not results:
                not_found = True
        except SpotifySearchError as e:
            error = str(e)

    return templates.TemplateResponse("songs/search.html", {
        "request": request,
        "q": q,
        "results": results,
        "error": error,
        "not_found": not_found,
        "bad_track": request.query_params.get("error") == "badid",
    })


@router.post("/songs")
def add_song(
    request: Request,
    spotify_track_id: str = Form(...),
    title: str = Form(...),
    artist: str = Form(...),
    album_art_url: str = Form(default=""),
    comment: str = Form(default=""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    # 手動入力は廃止（2026-07-02）。Spotify検索結果からの登録のみ受け付ける。
    # is_manual_entryフラグは既存データ互換のためモデルには残している。
    if not TRACK_ID_PATTERN.match(spotify_track_id):
        return RedirectResponse("/songs/search?error=badid", status_code=303)
    try:
        song_service.add_song(
            db,
            user_id=user_id,
            title=title,
            artist=artist,
            spotify_track_id=spotify_track_id,
            # ジャケットURLはhttpsのみ許可（不正URLの混入防止）
            album_art_url=album_art_url if album_art_url.startswith("https://") else None,
            is_manual_entry=False,
            comment=comment or None,
        )
    except SongLimitError:
        # PRGパターン: POSTに直接HTMLを返すとリロードで再送信されるためリダイレクト
        return RedirectResponse("/songs?error=limit", status_code=303)
    except SongDuplicateError:
        return RedirectResponse("/songs?error=duplicate", status_code=303)
    return RedirectResponse("/songs", status_code=303)


@router.post("/songs/{song_id}/activate")
def activate_song(song_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    """プール内の曲をマイ曲に切り替える"""
    try:
        song_service.set_active_song(db, song_id, user_id)
    except SongNotFoundError:
        pass
    return RedirectResponse("/songs", status_code=303)


@router.get("/songs/{song_id}/edit")
def edit_form(song_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    songs = song_service.get_songs(db, user_id)
    song = next((s for s in songs if s.song_id == song_id), None)
    if not song:
        return RedirectResponse("/songs", status_code=303)
    return templates.TemplateResponse("songs/edit.html", {"request": request, "song": song})


@router.post("/songs/{song_id}/edit")
def edit_song(
    song_id: int,
    title: str = Form(...),
    artist: str = Form(...),
    comment: str = Form(default=""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    try:
        song_service.update_song(db, song_id, user_id, title, artist, comment or None)
    except SongNotFoundError:
        pass
    return RedirectResponse("/songs", status_code=303)


@router.post("/songs/{song_id}/delete")
def delete_song(song_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    try:
        song_service.delete_song(db, song_id, user_id)
    except SongNotFoundError:
        pass
    return RedirectResponse("/songs", status_code=303)

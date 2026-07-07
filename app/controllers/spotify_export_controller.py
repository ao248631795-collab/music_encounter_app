"""
月間ベスト集をユーザー本人のSpotifyアカウントにプレイリストとして書き出すコントローラ。

フロー:
  POST /spotify/export        …… ボタン押下。未連携なら /spotify/connect へ、連携済みなら即書き出し
  GET  /spotify/connect       …… state署名 → Spotify認可画面へリダイレクト
  GET  /spotify/callback      …… 認可後の戻り。code交換 → refresh_token保存 → 書き出し

全ての戻りはPRGパターンで /calendar/monthly?... への303リダイレクト。
"""
import logging
from urllib.parse import urlencode, quote
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user_id, sign_spotify_state, verify_spotify_state
from app.models.user import User
from app.services import daily_pick_service
from app.services import spotify_user_client
from app.services.spotify_user_client import SpotifyUserAuthError

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _monthly_redirect(year: int, month: int, **params) -> RedirectResponse:
    """/calendar/monthly?year=&month=&... への303リダイレクトを組み立てる。"""
    query = {"year": year, "month": month}
    query.update(params)
    return RedirectResponse(f"/calendar/monthly?{urlencode(query)}", status_code=303)


def _do_export(db: Session, user: User, year: int, month: int, access_token) -> RedirectResponse:
    """
    共通の書き出し処理。
    access_token を渡された場合（callback直後）はそれをそのまま使う。
    None の場合は保存済みrefresh_tokenからaccess_tokenを取り直す（export経由）。
    """
    uris, skipped = daily_pick_service.collect_month_track_uris(db, user.user_id, year, month)
    if not uris:
        # callback経由等で対象0曲になった場合、空リストをAPIに投げない
        return _monthly_redirect(year, month, export="notracks")
    try:
        if access_token is None:
            # 保存済みrefresh_tokenからaccess_tokenを取得（新しいrefresh_tokenが返れば保存）
            token_data = spotify_user_client.refresh_access_token(user.spotify_refresh_token)
            access_token = token_data["access_token"]
            new_refresh = token_data.get("refresh_token")
            if new_refresh:
                user.spotify_refresh_token = new_refresh
                db.commit()

        playlist = spotify_user_client.create_playlist(
            access_token,
            name=f"すれ違いベスト {year}年{month}月",
            description="音楽すれ違いアプリで選んだデイリーベスト集",
        )
        try:
            spotify_user_client.add_tracks(access_token, playlist["id"], uris)
        except SpotifyUserAuthError:
            # 曲追加に失敗したら空プレイリストを残さない（ベストエフォートで削除）
            try:
                spotify_user_client.unfollow_playlist(access_token, playlist["id"])
            except SpotifyUserAuthError:
                pass
            raise
    except SpotifyUserAuthError as e:
        # 原因調査できるよう生エラーをログに残す（バナーは一般メッセージのまま）
        logger.warning("Spotify書き出し失敗 (user_id=%s, %s年%s月): %s", user.user_id, year, month, e)
        # refresh失敗（トークン失効）ならNULLに戻して再連携へ。それ以外はエラー表示。
        if access_token is None:
            user.spotify_refresh_token = None
            db.commit()
            return RedirectResponse(
                f"/spotify/connect?{urlencode({'year': year, 'month': month})}",
                status_code=303,
            )
        return _monthly_redirect(year, month, export="error")

    return _monthly_redirect(
        year, month,
        export="ok",
        added=len(uris),
        skipped=skipped,
        plurl=playlist["url"],
    )


@router.post("/spotify/export")
def export_playlist(
    year: int = Form(...),
    month: int = Form(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    uris, _ = daily_pick_service.collect_month_track_uris(db, user_id, year, month)
    if not uris:
        return _monthly_redirect(year, month, export="notracks")

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None or not user.spotify_refresh_token:
        # 未連携 → 認可フローへ
        return RedirectResponse(
            f"/spotify/connect?{urlencode({'year': year, 'month': month})}",
            status_code=303,
        )

    return _do_export(db, user, year, month, access_token=None)


@router.get("/spotify/connect")
def connect(
    year: int,
    month: int,
    user_id: int = Depends(get_current_user_id),
):
    state = sign_spotify_state(user_id, year, month)
    return RedirectResponse(spotify_user_client.get_authorize_url(state), status_code=303)


@router.get("/spotify/callback")
def callback(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    code = request.query_params.get("code")

    verified = verify_spotify_state(state)
    # state不正、またはstateのuser_idがログイン中ユーザーと不一致なら弾く
    if verified is None or verified[0] != user_id:
        return RedirectResponse("/calendar/monthly?export=error", status_code=303)

    _, year, month = verified

    # ユーザーが認可を拒否した場合
    if error:
        return _monthly_redirect(year, month, export="denied")

    if not code:
        return _monthly_redirect(year, month, export="error")

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        return RedirectResponse("/calendar/monthly?export=error", status_code=303)

    try:
        token_data = spotify_user_client.exchange_code(code)
    except SpotifyUserAuthError as e:
        logger.warning("Spotifyトークン交換失敗 (user_id=%s): %s", user_id, e)
        return _monthly_redirect(year, month, export="error")

    # refresh_tokenを保存し、交換直後のaccess_tokenをそのまま書き出しに使う
    user.spotify_refresh_token = token_data.get("refresh_token")
    db.commit()

    return _do_export(db, user, year, month, access_token=token_data["access_token"])

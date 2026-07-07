from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user_id
from app.services import daily_pick_service, playlist_service
from app.timeutil import today_app

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/playlist")
def show_playlist(request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    tracks = playlist_service.get_playlist(db, user_id)

    # 今日すれ違った曲は、このページから直接「今日のベスト」に選べる
    today = today_app()
    candidates = daily_pick_service.get_today_candidates(db, user_id, today)
    candidate_song_ids = {c["song_id"] for c in candidates}
    today_pick = daily_pick_service.get_pick(db, user_id, today)

    error = request.query_params.get("error")

    return templates.TemplateResponse("playlist/index.html", {
        "request": request,
        "tracks": tracks,
        "candidate_song_ids": candidate_song_ids,
        "today_pick": today_pick,
        "error": error,
    })

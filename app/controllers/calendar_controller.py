import calendar
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user_id
from app.services import daily_pick_service
from app.services.daily_pick_service import PickValidationError
from app.timeutil import now_app, today_app

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/calendar")
def calendar_view(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
    day: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    now = now_app()
    # year/month が無効または未指定なら現在（JST）の年月
    # （yearはdate()の許容範囲1〜9999に収まらないとValueErrorになるため範囲チェック）
    if (
        year is None or month is None
        or month < 1 or month > 12
        or year < 1 or year > 9999
    ):
        year = now.year
        month = now.month

    cal = calendar.Calendar(firstweekday=6)  # 日曜始まり
    weeks = cal.monthdayscalendar(year, month)

    # prev/next の年月
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    picks = daily_pick_service.get_picks_for_month(db, user_id, year, month)

    today = now.date()
    # 表示中の月に関係なく、今日の候補と今日のピックを常に渡す
    candidates = daily_pick_service.get_today_candidates(db, user_id, today)
    today_pick = daily_pick_service.get_pick(db, user_id, today)

    # 共鳴（レゾナンス）: グリッド表示用は表示中の月、バナー用は今日の属する月で判定
    resonance_days = daily_pick_service.get_resonance_days(db, user_id, year, month)
    if year == today.year and month == today.month:
        today_resonance = today.day in resonance_days
    else:
        today_resonance = today.day in daily_pick_service.get_resonance_days(
            db, user_id, today.year, today.month
        )
    today_resonance_count = daily_pick_service.get_today_resonance_count(db, user_id, today)
    picked_count = daily_pick_service.count_picked_by_others(db, user_id, today)

    selected_day = None
    selected_pick = None
    if day is not None and day in picks:
        selected_day = day
        selected_pick = picks[day]

    error = request.query_params.get("error")

    return templates.TemplateResponse("calendar/index.html", {
        "request": request,
        "year": year,
        "month": month,
        "weeks": weeks,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "picks": picks,
        "today": today,
        "candidates": candidates,
        "today_pick": today_pick,
        "selected_day": selected_day,
        "selected_pick": selected_pick,
        "resonance_days": resonance_days,
        "today_resonance": today_resonance,
        "today_resonance_count": today_resonance_count,
        "picked_count": picked_count,
        "error": error,
    })


@router.get("/calendar/monthly")
def monthly_playlist(
    request: Request,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    now = now_app()
    if (
        year is None or month is None
        or month < 1 or month > 12
        or year < 1 or year > 9999
    ):
        year = now.year
        month = now.month

    picks = daily_pick_service.get_monthly_playlist(db, user_id, year, month)
    resonance_days = daily_pick_service.get_resonance_days(db, user_id, year, month)

    # Spotify書き出し結果バナー用のクエリパラメータ（int変換は安全に）
    qp = request.query_params
    export = qp.get("export")

    def _safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    export_added = _safe_int(qp.get("added"))
    export_skipped = _safe_int(qp.get("skipped"))
    export_plurl = qp.get("plurl")

    return templates.TemplateResponse("calendar/monthly.html", {
        "request": request,
        "year": year,
        "month": month,
        "picks": picks,
        "resonance_days": resonance_days,
        "export": export,
        "export_added": export_added,
        "export_skipped": export_skipped,
        "export_plurl": export_plurl,
    })


@router.post("/calendar/pick")
def set_pick(
    song_id: int = Form(...),
    return_to: str = Form(default="calendar"),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    # 戻り先はホワイトリストで固定（オープンリダイレクト防止）
    dest = "/playlist" if return_to == "playlist" else "/calendar"
    try:
        daily_pick_service.set_daily_pick(db, user_id, song_id, today_app())
    except PickValidationError:
        return RedirectResponse(f"{dest}?error=invalid", status_code=303)
    return RedirectResponse(dest, status_code=303)

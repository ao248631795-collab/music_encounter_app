from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user_id
from app.services import encounter_service, location_service
from app.timeutil import today_app

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/locations")
def location_form(request: Request):
    registered = request.query_params.get("registered") == "1"
    bad_coords = request.query_params.get("error") == "badcoords"
    # partners: 登録直後のすれ違い人数（未登録アクセス時は-1で非表示）
    try:
        partners = int(request.query_params.get("partners", "-1"))
    except ValueError:
        partners = -1
    return templates.TemplateResponse("locations/register.html", {
        "request": request,
        "registered": registered,
        "bad_coords": bad_coords,
        "partners": partners,
    })


@router.post("/locations")
def register_location(
    latitude: float = Form(...),
    longitude: float = Form(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    # 緯度±90・経度±180の範囲外は拒否（不正データがすれ違い判定を汚染するのを防ぐ）
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return RedirectResponse("/locations?error=badcoords", status_code=303)
    location_service.register_location(db, user_id, latitude, longitude)
    # 登録と同時に、期限切れ位置情報の掃除→すれ違い判定を実行（2026-07-02変更。バッチ待ちを廃止）
    location_service.delete_expired_locations(db)
    encounter_service.run_encounter_batch(db)
    partners = encounter_service.count_partners_on(db, user_id, today_app())
    return RedirectResponse(f"/locations?registered=1&partners={partners}", status_code=303)

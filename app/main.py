from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from app.controllers import song_controller, location_controller, playlist_controller, calendar_controller, auth_controller, spotify_export_controller
from app.auth import auth_middleware, get_current_user_id
from app.db import get_db
from app.init_db import init_db
from app.services.encounter_service import count_partners_on, count_partners_total
from app.timeutil import today_app

app = FastAPI(title="音楽すれ違いアプリ")
templates = Jinja2Templates(directory="app/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 認証ミドルウェア（全リクエストに適用）
app.middleware("http")(auth_middleware)

app.include_router(auth_controller.router)
app.include_router(song_controller.router)
app.include_router(location_controller.router)
app.include_router(playlist_controller.router)
app.include_router(calendar_controller.router)
app.include_router(spotify_export_controller.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    today_count = count_partners_on(db, user_id, today_app())
    total_count = count_partners_total(db, user_id)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "today_count": today_count,
        "total_count": total_count,
    })

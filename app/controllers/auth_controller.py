from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import sign_user_id
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _set_session_cookie(response: RedirectResponse, user_id: int) -> None:
    """署名付きセッションCookieを付与する。"""
    token = sign_user_id(user_id)
    response.set_cookie("session", token, httponly=True, samesite="lax")


@router.get("/register")
def register_form(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register")
def register(
    request: Request,
    nickname: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != password_confirm:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": "パスワードが一致しません。",
            "nickname": nickname,
        })
    try:
        user = auth_service.register_user(db, nickname, password)
    except AuthError as e:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "error": str(e),
            "nickname": nickname,
        })
    # 登録成功 → 自動ログイン
    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, user.user_id)
    return response


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
def login(
    request: Request,
    nickname: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = auth_service.authenticate(db, nickname, password)
    if user is None:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "ニックネームまたはパスワードが違います。",
            "nickname": nickname,
        })
    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, user.user_id)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response

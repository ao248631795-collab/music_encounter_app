import hashlib
import hmac
from typing import Optional
from fastapi import Request
from fastapi.responses import RedirectResponse
from app.config import SECRET_KEY
from app.db import SessionLocal
from app.models.user import User

# 認証不要の公開パス（プレフィックス一致で判定）
PUBLIC_PATHS = ("/login", "/register", "/static", "/favicon.ico")


def sign_user_id(user_id: int) -> str:
    """user_id を HMAC-SHA256 で署名して "{user_id}.{signature}" 形式にする。"""
    sig = hmac.new(SECRET_KEY.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"


def verify_session_cookie(value: Optional[str]) -> Optional[int]:
    """
    署名付きCookie値を検証し、正しければ user_id を返す。
    形式不正・改ざんなら None。
    """
    if not value or "." not in value:
        return None
    raw_id, sig = value.rsplit(".", 1)
    if not raw_id.isdigit():
        return None
    expected = hmac.new(SECRET_KEY.encode(), raw_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    return int(raw_id)


def sign_spotify_state(user_id: int, year: int, month: int) -> str:
    """
    Spotify OAuth のstateパラメータをHMAC-SHA256で署名する（CSRF対策）。
    "{user_id}:{year}:{month}" を署名し "{payload}.{signature}" 形式にする。
    """
    payload = f"{user_id}:{year}:{month}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_spotify_state(state: Optional[str]) -> Optional[tuple]:
    """
    署名付きstateを検証し、正しければ (user_id, year, month) を返す。
    形式不正・改ざん・数値変換不可なら None。
    """
    if not state or "." not in state:
        return None
    payload, sig = state.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    parts = payload.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def get_current_user_id(request: Request) -> int:
    """ミドルウェアがセット済みの user_id を返す依存関数。"""
    return request.state.user_id


def _is_public_path(path: str) -> bool:
    for p in PUBLIC_PATHS:
        if path == p or path.startswith(p + "/"):
            return True
    return False


async def auth_middleware(request: Request, call_next):
    """
    セッションCookieを検証し request.state に user_id / user_nickname をセットする。
    未認証で非公開パスへのアクセスは /login にリダイレクト。
    認証済みで /login か /register へのGETは / にリダイレクト。
    """
    # 静的ファイル・faviconはテンプレート描画がなくユーザー情報不要のため、
    # Cookie検証もDBアクセスもせず素通しする（リクエストごとの無駄なクエリ防止）
    path = request.url.path
    if path.startswith("/static/") or path == "/favicon.ico":
        return await call_next(request)

    cookie = request.cookies.get("session")
    user_id = verify_session_cookie(cookie)

    request.state.user_id = user_id
    request.state.user_nickname = None

    # 有効なら nickname をDBから引いて表示用にセット
    if user_id is not None:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user is None:
                # ユーザーが存在しない（削除済み等）→未認証扱い
                user_id = None
                request.state.user_id = None
            else:
                request.state.user_nickname = user.nickname
        finally:
            db.close()

    is_public = _is_public_path(path)

    # 認証済みユーザーが /login か /register にGETアクセスしたら / へ
    if user_id is not None and request.method == "GET" and path in ("/login", "/register"):
        return RedirectResponse("/", status_code=303)

    # 未認証で非公開パスへのアクセスは /login へ
    if user_id is None and not is_public:
        return RedirectResponse("/login", status_code=303)

    return await call_next(request)

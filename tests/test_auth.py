import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
import app.models  # noqa: F401 — 全モデルをBaseに登録
from app.models.user import User
from app.services import auth_service
from app.services.auth_service import AuthError
from app.auth import sign_user_id, verify_session_cookie


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


# ===== hash / verify =====

def test_hash_then_verify_success():
    stored = auth_service.hash_password("demo1234")
    assert "$" in stored, "保存形式が salt$hash になっていない"
    assert auth_service.verify_password("demo1234", stored), "正しいパスワードでverify失敗"


def test_verify_wrong_password_fails():
    stored = auth_service.hash_password("demo1234")
    assert not auth_service.verify_password("wrongpass", stored), "誤パスワードでverify成功してしまった"


# ===== register_user =====

def test_register_user_success():
    db = make_session()
    user = auth_service.register_user(db, "Alice", "demo1234")
    assert user.user_id is not None, "user_idが採番されていない"
    assert user.nickname == "Alice"
    assert user.password_hash, "password_hashが設定されていない"
    db.close()


def test_register_duplicate_nickname_raises():
    db = make_session()
    auth_service.register_user(db, "Alice", "demo1234")
    raised = False
    try:
        auth_service.register_user(db, "Alice", "another12")
    except AuthError as e:
        raised = True
        assert "既に使われています" in str(e)
    assert raised, "nickname重複でAuthErrorが送出されなかった"
    db.close()


def test_register_short_password_raises():
    db = make_session()
    raised = False
    try:
        auth_service.register_user(db, "Bob", "1234567")  # 7文字
    except AuthError:
        raised = True
    assert raised, "パスワード7文字でAuthErrorが送出されなかった"
    db.close()


# ===== authenticate =====

def test_authenticate_success():
    db = make_session()
    auth_service.register_user(db, "Alice", "demo1234")
    user = auth_service.authenticate(db, "Alice", "demo1234")
    assert user is not None, "正しい資格情報で認証失敗"
    assert user.nickname == "Alice"
    db.close()


def test_authenticate_wrong_password_none():
    db = make_session()
    auth_service.register_user(db, "Alice", "demo1234")
    user = auth_service.authenticate(db, "Alice", "wrongpass")
    assert user is None, "誤パスワードでNoneが返らなかった"
    db.close()


def test_authenticate_unknown_nickname_none():
    db = make_session()
    auth_service.register_user(db, "Alice", "demo1234")
    user = auth_service.authenticate(db, "NoSuchUser", "demo1234")
    assert user is None, "存在しないnicknameでNoneが返らなかった"
    db.close()


# ===== session cookie 署名/検証 =====

def test_sign_and_verify_session_roundtrip():
    token = sign_user_id(42)
    assert verify_session_cookie(token) == 42, "署名Cookieの往復検証に失敗"


def test_verify_tampered_cookie_none():
    assert verify_session_cookie("1.deadbeef") is None, "改ざんCookieでNoneが返らなかった"


if __name__ == "__main__":
    test_hash_then_verify_success()
    test_verify_wrong_password_fails()
    test_register_user_success()
    test_register_duplicate_nickname_raises()
    test_register_short_password_raises()
    test_authenticate_success()
    test_authenticate_wrong_password_none()
    test_authenticate_unknown_nickname_none()
    test_sign_and_verify_session_roundtrip()
    test_verify_tampered_cookie_none()
    print("全テスト通過")

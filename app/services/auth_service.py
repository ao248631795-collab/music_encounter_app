import hashlib
import hmac
import secrets
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User


class AuthError(Exception):
    """認証・登録に関するユーザー向けエラー（メッセージ付き）"""
    pass


def hash_password(password: str) -> str:
    """
    パスワードをpbkdf2_hmac(sha256)でハッシュ化する。
    saltは secrets.token_hex(16)。保存形式は "{salt_hex}${hash_hex}"。
    """
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """保存済みハッシュと照合する。hmac.compare_digestで定数時間比較。"""
    if not stored or "$" not in stored:
        return False
    salt, expected_hex = stored.split("$", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return hmac.compare_digest(dk.hex(), expected_hex)


def register_user(db: Session, nickname: str, password: str) -> User:
    """
    新規ユーザーを登録する。
    - nicknameはstrip後1〜30文字
    - nickname重複チェック
    - パスワードは8文字以上
    OKなら User を作成してcommitし返す。
    """
    nickname = (nickname or "").strip()
    if len(nickname) < 1 or len(nickname) > 30:
        raise AuthError("ニックネームは1〜30文字で入力してください。")

    existing = db.query(User).filter(User.nickname == nickname).first()
    if existing is not None:
        raise AuthError("このニックネームは既に使われています。")

    if len(password) < 8:
        raise AuthError("パスワードは8文字以上で入力してください。")

    user = User(nickname=nickname, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, nickname: str, password: str) -> Optional[User]:
    """
    nickname一致かつpassword_hashがNULLでなくverify成功ならUser、それ以外None。
    """
    nickname = (nickname or "").strip()
    user = db.query(User).filter(User.nickname == nickname).first()
    if user is None:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

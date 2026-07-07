from datetime import datetime
from app.timeutil import now_app
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nickname: Mapped[Optional[str]] = mapped_column(nullable=True)
    # パスワードハッシュ（既存行がNULLでも動くようnullable）
    password_hash: Mapped[Optional[str]] = mapped_column(nullable=True)
    # SpotifyユーザーOAuthのrefresh_token（未連携ならNULL・トークン失効時もNULLに戻す）
    spotify_refresh_token: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=now_app)

    songs: Mapped[list["Song"]] = relationship("Song", back_populates="user", cascade="all, delete-orphan")
    locations: Mapped[list["Location"]] = relationship("Location", back_populates="user", cascade="all, delete-orphan")

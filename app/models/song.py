from datetime import datetime
from app.timeutil import now_app
from typing import Optional
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Song(Base):
    __tablename__ = "songs"

    song_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    spotify_track_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    artist: Mapped[str] = mapped_column(String(100), nullable=False)
    album_art_url: Mapped[Optional[str]] = mapped_column(nullable=True)
    is_manual_entry: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)  # マイ曲フラグ（プール内で1曲のみtrue）
    comment: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=now_app)

    user: Mapped["User"] = relationship("User", back_populates="songs")

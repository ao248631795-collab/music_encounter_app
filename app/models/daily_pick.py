from datetime import datetime, date
from app.timeutil import now_app
from typing import Optional
from sqlalchemy import ForeignKey, String, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class DailyPick(Base):
    __tablename__ = "daily_picks"
    # 1ユーザーにつき1日1件
    __table_args__ = (
        UniqueConstraint("user_id", "pick_date", name="uq_daily_picks_user_date"),
    )

    pick_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    pick_date: Mapped[date] = mapped_column(Date, nullable=False)  # どの日のベストか

    # 曲の所有者（共鳴判定の匿名集計にのみ使用。表示には使わない。
    # スナップショット原則の例外: 将来ユーザー削除機能を作る場合はNULL化して過去記録を守る）
    song_owner_id: Mapped[Optional[int]] = mapped_column(nullable=True)

    # 相手の曲のスナップショット（相手が後で曲を削除・編集しても思い出が壊れないようコピー保存）
    spotify_track_id: Mapped[Optional[str]] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    artist: Mapped[str] = mapped_column(String(100), nullable=False)
    album_art_url: Mapped[Optional[str]] = mapped_column(nullable=True)
    is_manual_entry: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=now_app)

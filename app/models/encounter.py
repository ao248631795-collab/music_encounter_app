from datetime import datetime
from sqlalchemy import ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Encounter(Base):
    __tablename__ = "encounters"
    # user_id_a < user_id_b を強制することで (A,B) と (B,A) の重複を防ぐ
    __table_args__ = (
        CheckConstraint("user_id_a < user_id_b", name="ck_encounters_ordered"),
        UniqueConstraint("user_id_a", "user_id_b", "encountered_at", name="uq_encounters_pair_day"),
    )

    encounter_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id_a: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    user_id_b: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    encountered_at: Mapped[datetime] = mapped_column(nullable=False)
    distance_m: Mapped[float] = mapped_column(nullable=False)

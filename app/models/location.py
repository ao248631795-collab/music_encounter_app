from datetime import datetime
from app.timeutil import now_app
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Location(Base):
    __tablename__ = "locations"

    location_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False, default=now_app)

    user: Mapped["User"] = relationship("User", back_populates="locations")

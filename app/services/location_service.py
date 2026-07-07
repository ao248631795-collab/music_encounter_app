import math
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.location import Location
from app.config import LOCATION_EXPIRE_HOURS
from app.timeutil import now_app

# 座標を約1kmグリッドに丸める（プライバシー対応）
_ROUND_DIGITS = 2


def register_location(db: Session, user_id: int, latitude: float, longitude: float) -> Location:
    lat = round(latitude, _ROUND_DIGITS)
    lon = round(longitude, _ROUND_DIGITS)
    loc = Location(user_id=user_id, latitude=lat, longitude=lon, recorded_at=now_app())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def delete_expired_locations(db: Session) -> int:
    cutoff = now_app() - timedelta(hours=LOCATION_EXPIRE_HOURS)
    deleted = db.query(Location).filter(Location.recorded_at < cutoff).delete()
    db.commit()
    return deleted

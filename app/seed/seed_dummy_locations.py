"""
デモ用ダミーデータ投入スクリプト。
使い方: python -m app.seed.seed_dummy_locations
"""
from datetime import datetime
from app.timeutil import now_app, timedelta
from app.db import SessionLocal
from app.models.user import User
from app.models.song import Song
from app.models.location import Location
from app.init_db import init_db

# 渋谷駅周辺の座標（緯度・経度）
BASE_LAT = 35.6580
BASE_LON = 139.7016

USERS = [
    {"nickname": "Alice"},
    {"nickname": "Bob"},
    {"nickname": "Carol"},
]

# is_active: 各ユーザー1曲のみtrue（マイ曲）。残りはプール曲
SONGS = [
    {"user_idx": 0, "title": "夜に駆ける", "artist": "YOASOBI", "spotify_track_id": None, "is_manual_entry": True, "is_active": True},
    {"user_idx": 0, "title": "Blinding Lights", "artist": "The Weeknd", "spotify_track_id": None, "is_manual_entry": True, "is_active": False},
    {"user_idx": 1, "title": "炎", "artist": "LiSA", "spotify_track_id": None, "is_manual_entry": True, "is_active": True},
    {"user_idx": 1, "title": "Shape of You", "artist": "Ed Sheeran", "spotify_track_id": None, "is_manual_entry": True, "is_active": False},
    {"user_idx": 2, "title": "Dynamite", "artist": "BTS", "spotify_track_id": None, "is_manual_entry": True, "is_active": True},
]

# ダミー位置情報: user0とuser1は近接（すれ違い発生）、user2は遠方
LOCATIONS = [
    {"user_idx": 0, "lat": BASE_LAT, "lon": BASE_LON, "minutes_ago": 20},
    {"user_idx": 1, "lat": BASE_LAT + 0.0005, "lon": BASE_LON + 0.0005, "minutes_ago": 25},
    {"user_idx": 2, "lat": BASE_LAT + 1.0, "lon": BASE_LON + 1.0, "minutes_ago": 20},
]


def seed():
    init_db()
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("すでにデータが存在します。スキップします。")
            return

        now = now_app()
        users = []
        for u in USERS:
            user = User(nickname=u["nickname"], created_at=now)
            db.add(user)
            users.append(user)
        db.flush()

        for s in SONGS:
            db.add(Song(
                user_id=users[s["user_idx"]].user_id,
                title=s["title"],
                artist=s["artist"],
                spotify_track_id=s.get("spotify_track_id"),
                is_manual_entry=s["is_manual_entry"],
                is_active=s["is_active"],
                updated_at=now,
            ))

        for loc in LOCATIONS:
            db.add(Location(
                user_id=users[loc["user_idx"]].user_id,
                latitude=round(loc["lat"], 4),
                longitude=round(loc["lon"], 4),
                recorded_at=now - timedelta(minutes=loc["minutes_ago"]),
            ))

        db.commit()
        print(f"ユーザー{len(USERS)}名・曲{len(SONGS)}件・位置情報{len(LOCATIONS)}件を投入しました。")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

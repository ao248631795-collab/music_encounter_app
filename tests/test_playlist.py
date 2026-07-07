import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
import app.models  # noqa: F401 — 全モデルをBaseに登録
from app.models.user import User
from app.models.song import Song
from app.models.encounter import Encounter
from app.services import playlist_service


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session()


def setup_data(db):
    u1 = User(nickname="U1")
    u2 = User(nickname="U2")
    db.add_all([u1, u2])
    db.commit()

    song = Song(user_id=u2.user_id, title="曲X", artist="アーティストX",
                spotify_track_id="trackX", is_active=True,
                comment="この曲が好き")
    db.add(song)
    db.add(Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id,
                     encountered_at=datetime(2026, 7, 3, 12, 0), distance_m=10.0))
    db.commit()
    return u1, u2, song


def test_playlist_includes_spotify_track_id():
    """Embedプレーヤー表示に必要なspotify_track_idが含まれる。"""
    db = make_session()
    u1, u2, song = setup_data(db)

    tracks = playlist_service.get_playlist(db, u1.user_id)
    assert len(tracks) == 1
    assert tracks[0]["spotify_track_id"] == "trackX", "track_idがプレイリストに含まれていない"
    db.close()


def test_playlist_dedupes_same_track():
    """同じ曲は複数回すれ違っても1件にまとまる（Embed数の上限を保証）。"""
    db = make_session()
    u1, u2, song = setup_data(db)

    # 別日のすれ違いを追加 → 同一曲なので重複しない
    db.add(Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id,
                     encountered_at=datetime(2026, 7, 2, 12, 0), distance_m=10.0))
    db.commit()

    tracks = playlist_service.get_playlist(db, u1.user_id)
    assert len(tracks) == 1, f"同一曲が重複している: {len(tracks)}件"
    db.close()


def test_playlist_includes_comment():
    """マイ曲の「ひとこと」(comment)がプレイリストのdictに含まれる（相手への公開）。"""
    db = make_session()
    u1, u2, song = setup_data(db)

    tracks = playlist_service.get_playlist(db, u1.user_id)
    assert len(tracks) == 1
    assert tracks[0]["comment"] == "この曲が好き", "commentがプレイリストに含まれていない"
    db.close()


def test_playlist_encounter_count_dedupes_but_counts():
    """同じ相手と2日すれ違うと encounter_count==2（曲は1行にdedupされたまま）。"""
    db = make_session()
    u1, u2, song = setup_data(db)

    # 別日のすれ違いを追加（同一ペア・別日 → encounterは2件、曲は1行にdedup）
    db.add(Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id,
                     encountered_at=datetime(2026, 7, 2, 12, 0), distance_m=10.0))
    db.commit()

    tracks = playlist_service.get_playlist(db, u1.user_id)
    assert len(tracks) == 1, f"同一曲が重複している: {len(tracks)}件"
    assert tracks[0]["encounter_count"] == 2, "すれ違い回数が2で集計されていない"
    db.close()


if __name__ == "__main__":
    test_playlist_includes_spotify_track_id()
    test_playlist_dedupes_same_track()
    test_playlist_includes_comment()
    test_playlist_encounter_count_dedupes_but_counts()
    print("全テスト通過")

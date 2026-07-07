import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
import app.models  # noqa: F401 — 全モデルをBaseに登録
from app.models.user import User
from app.services import song_service
from app.services.song_service import SongDuplicateError


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session()


def setup_user(db):
    user = User(nickname="U1")
    db.add(user)
    db.commit()
    return user


def test_duplicate_track_rejected():
    """同じspotify_track_idの曲はプールに重複登録できない。"""
    db = make_session()
    user = setup_user(db)

    song_service.add_song(db, user.user_id, "曲A", "アーティストA", spotify_track_id="t" * 22)
    raised = False
    try:
        song_service.add_song(db, user.user_id, "曲A(別名)", "アーティストA", spotify_track_id="t" * 22)
    except SongDuplicateError:
        raised = True
    assert raised, "重複登録でSongDuplicateErrorが送出されなかった"
    assert song_service.count_songs(db, user.user_id) == 1
    db.close()


def test_different_track_allowed():
    """別の曲は普通に登録できる。"""
    db = make_session()
    user = setup_user(db)

    song_service.add_song(db, user.user_id, "曲A", "アーティストA", spotify_track_id="a" * 22)
    song_service.add_song(db, user.user_id, "曲B", "アーティストB", spotify_track_id="b" * 22)
    assert song_service.count_songs(db, user.user_id) == 2
    db.close()


def test_update_spotify_song_locks_title_artist():
    """Spotify連携曲は曲名・アーティストを変更できない（コメントのみ更新可）。"""
    db = make_session()
    user = setup_user(db)

    song = song_service.add_song(db, user.user_id, "曲A", "アーティストA", spotify_track_id="a" * 22)
    updated = song_service.update_song(db, song.song_id, user.user_id,
                                       title="改ざん曲名", artist="改ざんアーティスト", comment="良い曲")
    assert updated.title == "曲A", "Spotify曲の曲名が変更されてしまった"
    assert updated.artist == "アーティストA", "Spotify曲のアーティストが変更されてしまった"
    assert updated.comment == "良い曲", "コメントが更新されていない"
    db.close()


def test_update_manual_song_allows_title_artist():
    """既存の手動曲（track_idなし）は従来どおり曲名・アーティストを変更できる。"""
    db = make_session()
    user = setup_user(db)

    song = song_service.add_song(db, user.user_id, "曲A", "アーティストA",
                                 spotify_track_id=None, is_manual_entry=True)
    updated = song_service.update_song(db, song.song_id, user.user_id,
                                       title="正しい曲名", artist="正しいアーティスト", comment=None)
    assert updated.title == "正しい曲名"
    assert updated.artist == "正しいアーティスト"
    db.close()


if __name__ == "__main__":
    test_duplicate_track_rejected()
    test_different_track_allowed()
    test_update_spotify_song_locks_title_artist()
    test_update_manual_song_allows_title_artist()
    print("全テスト通過")

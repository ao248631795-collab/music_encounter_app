from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.models.song import Song
from app.timeutil import now_app
from app.config import SONG_MAX_PER_USER


def get_songs(db: Session, user_id: int) -> list[Song]:
    return (
        db.query(Song)
        .filter(Song.user_id == user_id)
        .order_by(Song.updated_at.desc())
        .all()
    )


def count_songs(db: Session, user_id: int) -> int:
    return db.query(Song).filter(Song.user_id == user_id).count()


def get_active_song(db: Session, user_id: int) -> Optional[Song]:
    """マイ曲（is_active=trueの曲）を返す。未設定ならNone"""
    return (
        db.query(Song)
        .filter(Song.user_id == user_id, Song.is_active == True)  # noqa: E712
        .first()
    )


def set_active_song(db: Session, song_id: int, user_id: int) -> Song:
    """プール内の指定曲をマイ曲に切り替える（他の曲のis_activeは落とす）"""
    song = db.query(Song).filter(Song.song_id == song_id, Song.user_id == user_id).first()
    if not song:
        raise SongNotFoundError()
    db.query(Song).filter(Song.user_id == user_id).update({Song.is_active: False})
    song.is_active = True
    db.commit()
    db.refresh(song)
    return song


def add_song(
    db: Session,
    user_id: int,
    title: str,
    artist: str,
    spotify_track_id: Optional[str] = None,
    album_art_url: Optional[str] = None,
    is_manual_entry: bool = False,
    comment: Optional[str] = None,
) -> Song:
    if count_songs(db, user_id) >= SONG_MAX_PER_USER:
        raise SongLimitError(f"プールに保存できる曲は最大{SONG_MAX_PER_USER}曲です。")

    # 同じ曲の重複登録を防ぐ（Spotify曲はtrack_id、それ以外はtitle|artistで判定）
    existing = db.query(Song).filter(Song.user_id == user_id)
    if spotify_track_id:
        dup = existing.filter(Song.spotify_track_id == spotify_track_id).first()
    else:
        dup = existing.filter(Song.title == title, Song.artist == artist).first()
    if dup is not None:
        raise SongDuplicateError("この曲はすでにプールに登録されています。")

    # SQLiteはVARCHAR長を強制しないため、モデル定義の上限に合わせて切り詰める
    if comment:
        comment = comment[:200]

    song = Song(
        user_id=user_id,
        spotify_track_id=spotify_track_id,
        title=title,
        artist=artist,
        album_art_url=album_art_url,
        is_manual_entry=is_manual_entry,
        comment=comment,
        # マイ曲が未設定なら、追加した曲を自動的にマイ曲にする
        is_active=get_active_song(db, user_id) is None,
        updated_at=now_app(),
    )
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


def update_song(
    db: Session,
    song_id: int,
    user_id: int,
    title: str,
    artist: str,
    comment: Optional[str] = None,
) -> Song:
    song = db.query(Song).filter(Song.song_id == song_id, Song.user_id == user_id).first()
    if not song:
        raise SongNotFoundError()
    # Spotify連携曲は曲名・アーティストを変更不可（Embed再生との整合性を守る）。
    # 編集できるのはコメントのみ。手動登録の既存曲のみ曲名等を変更できる
    if song.spotify_track_id is None:
        song.title = title[:100]
        song.artist = artist[:100]
    # SQLiteはVARCHAR長を強制しないため、モデル定義の上限に合わせて切り詰める
    song.comment = comment[:200] if comment else comment
    song.updated_at = now_app()
    db.commit()
    db.refresh(song)
    return song


def delete_song(db: Session, song_id: int, user_id: int) -> None:
    song = db.query(Song).filter(Song.song_id == song_id, Song.user_id == user_id).first()
    if not song:
        raise SongNotFoundError()
    db.delete(song)
    db.commit()


class SongDuplicateError(Exception):
    """同じ曲をプールに重複登録しようとしたときのエラー"""
    pass


class SongLimitError(Exception):
    pass


class SongNotFoundError(Exception):
    pass

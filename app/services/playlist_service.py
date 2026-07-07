from sqlalchemy.orm import Session
from app.models.encounter import Encounter
from app.models.song import Song


def get_playlist(db: Session, user_id: int) -> list[dict]:
    """
    user_idとすれ違ったユーザーのマイ曲（is_active=true）を集約し、重複なく返す。
    プールに保存されているだけの曲（非アクティブ）は公開されない。
    並び順: すれ違い日時が新しい順。
    """
    encounters = (
        db.query(Encounter)
        .filter((Encounter.user_id_a == user_id) | (Encounter.user_id_b == user_id))
        .order_by(Encounter.encountered_at.desc())
        .all()
    )

    # 追加クエリを発行せず、ロード済みのencountersから相手ごとの
    # すれ違い成立回数（=日数。同一ペア同一日は1件になる既存仕様）を集計する。
    encounter_counts: dict[int, int] = {}
    for enc in encounters:
        partner_id = enc.user_id_b if enc.user_id_a == user_id else enc.user_id_a
        encounter_counts[partner_id] = encounter_counts.get(partner_id, 0) + 1

    seen_track_keys: set[str] = set()
    result: list[dict] = []

    for enc in encounters:
        partner_id = enc.user_id_b if enc.user_id_a == user_id else enc.user_id_a
        songs = (
            db.query(Song)
            .filter(Song.user_id == partner_id, Song.is_active == True)  # noqa: E712
            .all()
        )
        for song in songs:
            # Spotify曲はtrack_idで、手動曲は"title|artist"で重複判定
            key = song.spotify_track_id or f"{song.title}|{song.artist}"
            if key in seen_track_keys:
                continue
            seen_track_keys.add(key)
            result.append({
                "song_id": song.song_id,
                "spotify_track_id": song.spotify_track_id,
                "title": song.title,
                "artist": song.artist,
                "album_art_url": song.album_art_url,
                "is_manual_entry": song.is_manual_entry,
                "comment": song.comment,
                "encounter_count": encounter_counts.get(partner_id, 0),
                "encountered_at": enc.encountered_at,
            })

    return result

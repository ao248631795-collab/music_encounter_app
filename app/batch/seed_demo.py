"""
デモ用シードスクリプト（何度実行しても安全な冪等設計）。

使い方: python -m app.batch.seed_demo

実行すると「今日」（JST基準）を軸に以下を再現する:
- デモユーザー Alice / Bob / Carol（パスワード: demo1234）
- 各自のマイ曲（Alice: 夜に駆ける / Bob: 炎 / Carol: Dynamite）
- 今日の3人のすれ違い（同一スポットの位置情報→判定実行）
- 昨日のすれ違い（Alice-Bob）と Alice の昨日のベスト（炎）
- 今日の共鳴（Alice⇄Carol が互いの曲をベストに選び合った状態）

デモ当日の朝にこれを1回実行すれば、カレンダー・プレイリスト・
共鳴バナーがすべて「今日」の状態で見られる。
"""
from datetime import timedelta

from app.db import SessionLocal
from app.models.user import User
from app.models.song import Song
from app.models.location import Location
from app.models.encounter import Encounter
from app.models.daily_pick import DailyPick
from app.services.auth_service import hash_password
from app.services.encounter_service import run_encounter_batch
from app.services.location_service import delete_expired_locations
from app.services.daily_pick_service import set_daily_pick, get_pick
from app.timeutil import now_app

DEMO_PASSWORD = "demo1234"

DEMO_USERS = [
    # (nickname, [(title, artist, spotify_track_id, is_active, comment)])
    ("Alice", [("夜に駆ける", "YOASOBI", None, True, "イントロで夏を思い出す")]),
    ("Bob", [("炎", "LiSA", None, True, "落ち込んだ日はいつもこれ")]),
    ("Carol", [("Dynamite", "BTS", None, True, "朝の通勤で聴くと元気が出る")]),
]

# 全員同じスポット（渋谷駅）ですれ違う
SPOT = (35.6580, 139.7016)


def _ensure_user(db, nickname):
    user = db.query(User).filter(User.nickname == nickname).first()
    if user is None:
        user = User(nickname=nickname, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"  作成: ユーザー {nickname}")
    elif not user.password_hash:
        user.password_hash = hash_password(DEMO_PASSWORD)
        db.commit()
    return user


def _resolve_track(title, artist):
    """
    Spotify検索でtrack_idとジャケットURLを解決する（ベストエフォート）。
    オフラインや認証エラーでも落とさずNoneを返す。
    """
    try:
        from app.services.spotify_client import search_tracks
        results = search_tracks(f"{title} {artist}")
        if results:
            return results[0]["spotify_track_id"], results[0].get("album_art_url")
    except Exception:
        pass
    return None, None


def _ensure_song(db, user, title, artist, track_id, is_active, comment=None):
    song = db.query(Song).filter(Song.user_id == user.user_id, Song.title == title).first()
    if song is None:
        song = Song(user_id=user.user_id, title=title, artist=artist,
                    spotify_track_id=track_id, is_manual_entry=False,
                    is_active=is_active, comment=comment)
        db.add(song)
        db.commit()
        db.refresh(song)
        print(f"  作成: {user.nickname} の曲「{title}」")
    # ひとことは未設定（None）の場合のみ設定（本人の入力を上書きしない）
    if comment is not None and song.comment is None:
        song.comment = comment
        db.commit()
        print(f"  設定: 「{title}」にひとことを追加")
    # track_id未取得の曲はSpotify検索で補完（Embedプレーヤー再生用）
    if song.spotify_track_id is None:
        resolved_id, art_url = _resolve_track(title, artist)
        if resolved_id:
            song.spotify_track_id = resolved_id
            if song.album_art_url is None:
                song.album_art_url = art_url
            song.is_manual_entry = False
            db.commit()
            print(f"  補完: 「{title}」にSpotify track_idを設定")
    if is_active and not song.is_active:
        # マイ曲が別の曲になっていたら戻す
        db.query(Song).filter(Song.user_id == user.user_id).update({"is_active": False})
        song.is_active = True
        db.commit()
    return song


def _backfill_pick_track_ids(db):
    """
    track_id未保存の過去ピック（スナップショット）を、同名曲のSpotify情報で補完する。
    Embedプレーヤーで月間ベスト集を再生できるようにするための後方互換処理。
    """
    picks = db.query(DailyPick).filter(DailyPick.spotify_track_id.is_(None)).all()
    fixed = 0
    for pick in picks:
        song = (
            db.query(Song)
            .filter(Song.title == pick.title, Song.artist == pick.artist,
                    Song.spotify_track_id.isnot(None))
            .first()
        )
        if song:
            pick.spotify_track_id = song.spotify_track_id
            if pick.album_art_url is None:
                pick.album_art_url = song.album_art_url
            pick.is_manual_entry = False
            fixed += 1
    if fixed:
        db.commit()
        print(f"  補完: 過去ピック{fixed}件にSpotify情報を反映")


def _ensure_encounter(db, user_a, user_b, when, distance_m=10.0):
    a, b = sorted([user_a.user_id, user_b.user_id])
    day_start = when.replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (
        db.query(Encounter)
        .filter(
            Encounter.user_id_a == a,
            Encounter.user_id_b == b,
            Encounter.encountered_at >= day_start,
            Encounter.encountered_at < day_start + timedelta(days=1),
        )
        .first()
    )
    if existing is None:
        db.add(Encounter(user_id_a=a, user_id_b=b, encountered_at=when, distance_m=distance_m))
        db.commit()
        print(f"  作成: すれ違い {a}-{b} @ {when.date()}")


def main():
    db = SessionLocal()
    try:
        now = now_app()
        today = now.date()
        yesterday = today - timedelta(days=1)
        day_before_yesterday = today - timedelta(days=2)
        print(f"=== デモデータ投入（今日 = {today} / JST基準）===")

        # 1) ユーザーとマイ曲
        users = {}
        songs = {}
        for nickname, song_defs in DEMO_USERS:
            user = _ensure_user(db, nickname)
            users[nickname] = user
            for title, artist, track_id, is_active, comment in song_defs:
                songs[title] = _ensure_song(db, user, title, artist, track_id, is_active, comment)

        # 2) 今日のすれ違い: 3人が同じスポットに位置登録 → 判定実行
        for user in users.values():
            db.add(Location(user_id=user.user_id, latitude=SPOT[0], longitude=SPOT[1],
                            recorded_at=now))
        db.commit()
        delete_expired_locations(db)
        new_enc = run_encounter_batch(db)
        print(f"  今日のすれ違い判定: 新規{new_enc}件")

        # 3) 昨日のすれ違い（Alice-Bob）と Alice の昨日のベスト（炎）
        yesterday_noon = now.replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)
        _ensure_encounter(db, users["Alice"], users["Bob"], yesterday_noon)
        if get_pick(db, users["Alice"].user_id, yesterday) is None:
            set_daily_pick(db, users["Alice"].user_id, songs["炎"].song_id, yesterday)
            print("  作成: Alice の昨日のベスト = 炎")

        # 3b) 一昨日の共鳴（Alice⇄Carol）: 今日の共鳴を「2回目」にするための過去実績
        dby_noon = now.replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=2)
        _ensure_encounter(db, users["Alice"], users["Carol"], dby_noon)
        if get_pick(db, users["Alice"].user_id, day_before_yesterday) is None:
            set_daily_pick(db, users["Alice"].user_id, songs["Dynamite"].song_id, day_before_yesterday)
            print("  作成: Alice の一昨日のベスト = Dynamite（Carolの曲）")
        if get_pick(db, users["Carol"].user_id, day_before_yesterday) is None:
            set_daily_pick(db, users["Carol"].user_id, songs["夜に駆ける"].song_id, day_before_yesterday)
            print("  作成: Carol の一昨日のベスト = 夜に駆ける（Aliceの曲）")

        # 4) 今日の共鳴: Alice⇄Carol が互いの曲を選び合う
        set_daily_pick(db, users["Alice"].user_id, songs["Dynamite"].song_id, today)
        set_daily_pick(db, users["Carol"].user_id, songs["夜に駆ける"].song_id, today)
        print("  作成: 今日の共鳴（Alice⇄Carol）")

        # 5) 過去ピックのSpotify情報補完（月間ベスト集のEmbed再生用）
        _backfill_pick_track_ids(db)

        print("=== 完了 ===")
        print(f"ログイン: Alice / Bob / Carol（パスワード: {DEMO_PASSWORD}）")
        print("Aliceでカレンダーを開くと ✨共鳴バナー、昨日のセルに過去記録が見えます。")
    finally:
        db.close()


if __name__ == "__main__":
    main()

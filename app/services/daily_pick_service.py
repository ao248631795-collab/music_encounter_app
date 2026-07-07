from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Set
from sqlalchemy.orm import Session
from app.models.encounter import Encounter
from app.models.song import Song
from app.models.daily_pick import DailyPick


class PickValidationError(Exception):
    """デイリーピックの登録条件を満たさないときに送出する。"""
    pass


def _day_range(target_date: date):
    """target_date当日 [00:00, 翌日00:00) の範囲を返す。"""
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    return start, end


def _partner_ids_on(db: Session, user_id: int, target_date: date) -> List[int]:
    """target_date当日に user_id とすれ違った相手の user_id 一覧。"""
    start, end = _day_range(target_date)
    encounters = (
        db.query(Encounter)
        .filter(
            (Encounter.user_id_a == user_id) | (Encounter.user_id_b == user_id),
            Encounter.encountered_at >= start,
            Encounter.encountered_at < end,
        )
        .all()
    )
    partners = []
    for enc in encounters:
        partner_id = enc.user_id_b if enc.user_id_a == user_id else enc.user_id_a
        partners.append(partner_id)
    return partners


def get_today_candidates(db: Session, user_id: int, target_date: date) -> List[Dict]:
    """
    target_date当日にすれ違った相手のマイ曲（is_active=True）を重複なく返す。
    匿名性要件のため相手のnicknameは含めない。
    """
    partner_ids = _partner_ids_on(db, user_id, target_date)

    seen_track_keys = set()
    result: List[Dict] = []

    for partner_id in partner_ids:
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
            })

    return result


def get_pick(db: Session, user_id: int, target_date: date) -> Optional[DailyPick]:
    return (
        db.query(DailyPick)
        .filter(DailyPick.user_id == user_id, DailyPick.pick_date == target_date)
        .first()
    )


def _month_range(year: int, month: int):
    """その月 [1日, 翌月1日) の date 範囲を返す。"""
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1)
    else:
        month_end = date(year, month + 1, 1)
    return month_start, month_end


def get_picks_for_month(db: Session, user_id: int, year: int, month: int) -> Dict[int, DailyPick]:
    """その月の DailyPick を {日(int): DailyPick} で返す。"""
    month_start, month_end = _month_range(year, month)
    picks = (
        db.query(DailyPick)
        .filter(
            DailyPick.user_id == user_id,
            DailyPick.pick_date >= month_start,
            DailyPick.pick_date < month_end,
        )
        .all()
    )
    return {p.pick_date.day: p for p in picks}


def get_monthly_playlist(db: Session, user_id: int, year: int, month: int) -> List[DailyPick]:
    """その月に登録したデイリーベストを日付順（昇順）で並べたプレイリストを返す。"""
    month_start, month_end = _month_range(year, month)
    return (
        db.query(DailyPick)
        .filter(
            DailyPick.user_id == user_id,
            DailyPick.pick_date >= month_start,
            DailyPick.pick_date < month_end,
        )
        .order_by(DailyPick.pick_date.asc())
        .all()
    )


def collect_month_track_uris(db: Session, user_id: int, year: int, month: int) -> tuple:
    """その月のデイリーベストのSpotifyトラックURI一覧と、track_idが無くスキップした曲数を返す。
    戻り値: (uris: List[str], skipped: int)。URIは "spotify:track:{id}" 形式・日付昇順・
    重複もそのまま（日記としての順序を優先）。"""
    picks = get_monthly_playlist(db, user_id, year, month)
    uris: List[str] = []
    skipped = 0
    for pick in picks:
        if pick.spotify_track_id:
            uris.append(f"spotify:track:{pick.spotify_track_id}")
        else:
            skipped += 1
    return uris, skipped


def count_picked_by_others(db: Session, user_id: int, target_date: date) -> int:
    """
    target_dateに自分の曲を誰かがベストに選んだ件数を返す（匿名集計）。
    誰が選んだかは返さない（匿名性要件）。
    """
    return (
        db.query(DailyPick)
        .filter(
            DailyPick.song_owner_id == user_id,
            DailyPick.user_id != user_id,
            DailyPick.pick_date == target_date,
        )
        .count()
    )


def get_resonance_days(db: Session, user_id: int, year: int, month: int) -> Set[int]:
    """
    その月で「共鳴」が成立した日(int)の集合を返す。
    共鳴 = 同じ日に、自分が相手の曲を、相手が自分の曲を互いにベストに選び合ったこと。
    相手が誰かは返さない（匿名性要件）。
    """
    month_start, month_end = _month_range(year, month)

    # 自分のピック（曲の所有者が分かるものだけ）
    my_picks = (
        db.query(DailyPick)
        .filter(
            DailyPick.user_id == user_id,
            DailyPick.pick_date >= month_start,
            DailyPick.pick_date < month_end,
            DailyPick.song_owner_id.isnot(None),
        )
        .all()
    )
    if not my_picks:
        return set()

    # 自分の曲を選んでくれたピックを (選んだ人, 日付) で索引化
    picked_mine = (
        db.query(DailyPick)
        .filter(
            DailyPick.song_owner_id == user_id,
            DailyPick.pick_date >= month_start,
            DailyPick.pick_date < month_end,
        )
        .all()
    )
    keyed = {(q.user_id, q.pick_date) for q in picked_mine}

    return {
        p.pick_date.day
        for p in my_picks
        if (p.song_owner_id, p.pick_date) in keyed
    }


def get_today_resonance_count(db: Session, user_id: int, target_date: date) -> int:
    """target_dateに共鳴が成立している場合、その相手との累計共鳴回数（target_date含む）を返す。
    成立していなければ0。相手が誰かは返さない（匿名性）。

    実装: 自分のtarget_dateのピックのsong_owner_id（=相手X）を取得 →
    Xのtarget_dateのピックのsong_owner_idが自分なら共鳴成立 →
    全期間で「自分がXの曲を選んだ日」と「Xが自分の曲を選んだ日」の共通日付数を返す。
    """
    my_pick = get_pick(db, user_id, target_date)
    if my_pick is None or my_pick.song_owner_id is None:
        return 0

    partner_id = my_pick.song_owner_id

    # 相手Xのtarget_dateのピックが「自分の曲」でなければ共鳴は成立していない
    partner_pick = get_pick(db, partner_id, target_date)
    if partner_pick is None or partner_pick.song_owner_id != user_id:
        return 0

    # 全期間で「自分がXの曲を選んだ日」の集合
    my_days = {
        p.pick_date
        for p in db.query(DailyPick)
        .filter(DailyPick.user_id == user_id, DailyPick.song_owner_id == partner_id)
        .all()
    }
    # 全期間で「Xが自分の曲を選んだ日」の集合
    partner_days = {
        p.pick_date
        for p in db.query(DailyPick)
        .filter(DailyPick.user_id == partner_id, DailyPick.song_owner_id == user_id)
        .all()
    }

    return len(my_days & partner_days)


def set_daily_pick(db: Session, user_id: int, song_id: int, target_date: date) -> DailyPick:
    """
    target_dateのベスト曲を登録（1日1件のupsert）。
    検証: 対象Songが存在し is_active=True、所有者がuser_id本人でなく、
    所有者とuser_idの間にtarget_date当日のencounterがあること。
    """
    song = db.query(Song).filter(Song.song_id == song_id).first()
    if song is None:
        raise PickValidationError("指定された曲が存在しません。")
    if not song.is_active:
        raise PickValidationError("この曲は公開されていません。")
    if song.user_id == user_id:
        raise PickValidationError("自分の曲は登録できません。")

    partner_ids = _partner_ids_on(db, user_id, target_date)
    if song.user_id not in partner_ids:
        raise PickValidationError("この曲は当日のすれ違い履歴にありません。")

    pick = get_pick(db, user_id, target_date)
    if pick is None:
        pick = DailyPick(
            user_id=user_id,
            pick_date=target_date,
            song_owner_id=song.user_id,
            spotify_track_id=song.spotify_track_id,
            title=song.title,
            artist=song.artist,
            album_art_url=song.album_art_url,
            is_manual_entry=song.is_manual_entry,
        )
        db.add(pick)
    else:
        # 既存pickをスナップショット上書き更新
        pick.song_owner_id = song.user_id
        pick.spotify_track_id = song.spotify_track_id
        pick.title = song.title
        pick.artist = song.artist
        pick.album_art_url = song.album_art_url
        pick.is_manual_entry = song.is_manual_entry

    db.commit()
    db.refresh(pick)
    return pick

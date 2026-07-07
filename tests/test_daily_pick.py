import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
import app.models  # noqa: F401 — 全モデルをBaseに登録
from app.models.user import User
from app.models.song import Song
from app.models.encounter import Encounter
from app.models.daily_pick import DailyPick
from app.services import daily_pick_service
from app.services.daily_pick_service import PickValidationError


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def setup_data(db):
    """User1, User2 と曲・今日のEncounterを用意する。"""
    u1 = User(nickname="User1")
    u2 = User(nickname="User2")
    db.add_all([u1, u2])
    db.commit()

    # User2: 公開曲X（is_active=True）と 非公開曲Y（is_active=False）
    song_x = Song(user_id=u2.user_id, title="曲X", artist="アーティストX",
                  spotify_track_id="trackX", is_active=True)
    song_y = Song(user_id=u2.user_id, title="曲Y", artist="アーティストY",
                  spotify_track_id="trackY", is_active=False)
    db.add_all([song_x, song_y])
    db.commit()

    # 今日のEncounter(1,2)
    today = datetime.utcnow().date()
    enc = Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id,
                    encountered_at=datetime.utcnow(), distance_m=42.0)
    db.add(enc)
    db.commit()

    return u1, u2, song_x, song_y, today


def test_candidates_contains_active_only():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    candidates = daily_pick_service.get_today_candidates(db, u1.user_id, today)
    titles = [c["title"] for c in candidates]
    assert "曲X" in titles, "公開曲Xが候補に含まれていない"
    assert "曲Y" not in titles, "非公開曲Yが候補に含まれてしまっている"
    # nickname を含めない（匿名性）
    for c in candidates:
        assert "nickname" not in c, "候補にnicknameが含まれている"
    db.close()


def test_set_and_get_pick_snapshot():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    pick = daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    got = daily_pick_service.get_pick(db, u1.user_id, today)
    assert got is not None, "ピックが取得できない"
    assert got.title == "曲X", "スナップショットのtitle不一致"
    assert got.artist == "アーティストX", "スナップショットのartist不一致"
    assert got.spotify_track_id == "trackX", "スナップショットのtrack_id不一致"
    db.close()


def test_upsert_no_duplicate():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    count = db.query(DailyPick).filter(
        DailyPick.user_id == u1.user_id, DailyPick.pick_date == today
    ).count()
    assert count == 1, f"upsertされず {count} 件になっている"
    db.close()


def test_inactive_song_rejected():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    raised = False
    try:
        daily_pick_service.set_daily_pick(db, u1.user_id, song_y.song_id, today)
    except PickValidationError:
        raised = True
    assert raised, "非公開曲Yで PickValidationError が送出されなかった"
    db.close()


def test_yesterday_candidates_empty():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    yesterday = today - timedelta(days=1)
    candidates = daily_pick_service.get_today_candidates(db, u1.user_id, yesterday)
    assert candidates == [], "昨日の候補が空でない"
    db.close()


def test_monthly_playlist_ordered_by_date():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    # 同月内の複数日にピックを直接投入（日付順が昇順で返ることを確認）
    d10 = today.replace(day=10)
    d3 = today.replace(day=3)
    d20 = today.replace(day=20)
    for d in (d10, d3, d20):
        db.add(DailyPick(user_id=u1.user_id, pick_date=d,
                         title=f"曲{d.day}", artist="A", is_manual_entry=False))
    db.commit()

    picks = daily_pick_service.get_monthly_playlist(db, u1.user_id, today.year, today.month)
    days = [p.pick_date.day for p in picks]
    assert days == sorted(days), f"日付昇順で並んでいない: {days}"
    assert 3 in days and 10 in days and 20 in days, "同月のピックが欠けている"
    db.close()


def test_monthly_playlist_excludes_other_months():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    # 翌月のピックは今月のプレイリストに含めない
    next_month_day = (today.replace(day=1) + timedelta(days=40)).replace(day=5)
    db.add(DailyPick(user_id=u1.user_id, pick_date=next_month_day,
                     title="翌月曲", artist="A", is_manual_entry=False))
    db.commit()

    picks = daily_pick_service.get_monthly_playlist(db, u1.user_id, today.year, today.month)
    titles = [p.title for p in picks]
    assert "翌月曲" not in titles, "翌月のピックが今月に混入している"
    db.close()


def _give_u1_active_song(db, u1):
    """u1にもマイ曲を持たせる（共鳴テスト用）。"""
    song_a = Song(user_id=u1.user_id, title="曲A", artist="アーティストA",
                  spotify_track_id="trackA", is_active=True)
    db.add(song_a)
    db.commit()
    return song_a


def test_pick_records_song_owner():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    pick = daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    assert pick.song_owner_id == u2.user_id, "song_owner_idが記録されていない"
    db.close()


def test_count_picked_by_others():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)

    # u1がu2の曲を選ぶ → u2の被選出は1、u1の被選出は0
    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    assert daily_pick_service.count_picked_by_others(db, u2.user_id, today) == 1
    assert daily_pick_service.count_picked_by_others(db, u1.user_id, today) == 0
    db.close()


def test_resonance_mutual_same_day():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)
    song_a = _give_u1_active_song(db, u1)

    # 相互に選び合う → 両者に共鳴が成立
    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    daily_pick_service.set_daily_pick(db, u2.user_id, song_a.song_id, today)

    assert today.day in daily_pick_service.get_resonance_days(db, u1.user_id, today.year, today.month)
    assert today.day in daily_pick_service.get_resonance_days(db, u2.user_id, today.year, today.month)
    db.close()


def test_no_resonance_one_way():
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)
    _give_u1_active_song(db, u1)

    # u1だけが選ぶ（片方向）→ 共鳴しない
    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)

    assert daily_pick_service.get_resonance_days(db, u1.user_id, today.year, today.month) == set()
    assert daily_pick_service.get_resonance_days(db, u2.user_id, today.year, today.month) == set()
    db.close()


def test_today_resonance_count_single_day():
    """(a) 相互ピック1日のみ → count は 1。"""
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)
    song_a = _give_u1_active_song(db, u1)

    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    daily_pick_service.set_daily_pick(db, u2.user_id, song_a.song_id, today)

    assert daily_pick_service.get_today_resonance_count(db, u1.user_id, today) == 1
    assert daily_pick_service.get_today_resonance_count(db, u2.user_id, today) == 1
    db.close()


def test_today_resonance_count_two_days():
    """(b) 2日相互ピック → 2日目の count は 2。"""
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)
    song_a = _give_u1_active_song(db, u1)

    yesterday = today - timedelta(days=1)
    # 前日のすれ違い（set_daily_pickの当日encounter検証を満たすため）
    db.add(Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id,
                     encountered_at=datetime.combine(yesterday, datetime.min.time().replace(hour=12)),
                     distance_m=42.0))
    db.commit()

    # 前日に相互ピック
    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, yesterday)
    daily_pick_service.set_daily_pick(db, u2.user_id, song_a.song_id, yesterday)
    # 今日も相互ピック
    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)
    daily_pick_service.set_daily_pick(db, u2.user_id, song_a.song_id, today)

    assert daily_pick_service.get_today_resonance_count(db, u1.user_id, today) == 2
    assert daily_pick_service.get_today_resonance_count(db, u2.user_id, today) == 2
    db.close()


def test_today_resonance_count_one_way_zero():
    """(c) 片方向のみ → count は 0。"""
    db = make_session()
    u1, u2, song_x, song_y, today = setup_data(db)
    _give_u1_active_song(db, u1)

    # u1だけが選ぶ（相手は選び返していない）→ 共鳴不成立
    daily_pick_service.set_daily_pick(db, u1.user_id, song_x.song_id, today)

    assert daily_pick_service.get_today_resonance_count(db, u1.user_id, today) == 0
    assert daily_pick_service.get_today_resonance_count(db, u2.user_id, today) == 0
    db.close()


if __name__ == "__main__":
    test_candidates_contains_active_only()
    test_set_and_get_pick_snapshot()
    test_upsert_no_duplicate()
    test_inactive_song_rejected()
    test_yesterday_candidates_empty()
    test_monthly_playlist_ordered_by_date()
    test_monthly_playlist_excludes_other_months()
    test_pick_records_song_owner()
    test_count_picked_by_others()
    test_resonance_mutual_same_day()
    test_no_resonance_one_way()
    test_today_resonance_count_single_day()
    test_today_resonance_count_two_days()
    test_today_resonance_count_one_way_zero()
    print("全テスト通過")

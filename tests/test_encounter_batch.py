import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
import app.models  # noqa: F401 — 全モデルをBaseに登録
from app.models.user import User
from app.models.location import Location
from app.models.encounter import Encounter
from app.services import encounter_service


def make_session():
    # 本番と同条件（autoflush=False）で作る。バッチの重複バグはこの設定で再現していた
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session()


def setup_users(db):
    u1 = User(nickname="U1")
    u2 = User(nickname="U2")
    db.add_all([u1, u2])
    db.commit()
    return u1, u2


def test_no_duplicate_within_single_run():
    """条件を満たす位置ペアが複数あっても、同一ペア・同一日のencounterは1件だけ。"""
    db = make_session()
    u1, u2 = setup_users(db)

    base = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    # u1×1件、u2×2件 → 条件を満たすペアが2組できる
    db.add_all([
        Location(user_id=u1.user_id, latitude=35.0, longitude=135.0, recorded_at=base),
        Location(user_id=u2.user_id, latitude=35.0, longitude=135.0, recorded_at=base + timedelta(minutes=1)),
        Location(user_id=u2.user_id, latitude=35.0, longitude=135.0, recorded_at=base + timedelta(minutes=2)),
    ])
    db.commit()

    new_count = encounter_service.run_encounter_batch(db)
    total = db.query(Encounter).count()
    assert new_count == 1, f"新規件数が1でない: {new_count}"
    assert total == 1, f"同一ペア・同一日のencounterが重複している: {total}件"
    db.close()


def test_no_duplicate_across_runs():
    """バッチを2回実行しても同じすれ違いは再登録されない。"""
    db = make_session()
    u1, u2 = setup_users(db)

    base = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    db.add_all([
        Location(user_id=u1.user_id, latitude=35.0, longitude=135.0, recorded_at=base),
        Location(user_id=u2.user_id, latitude=35.0, longitude=135.0, recorded_at=base),
    ])
    db.commit()

    first = encounter_service.run_encounter_batch(db)
    second = encounter_service.run_encounter_batch(db)
    assert first == 1, f"1回目の新規件数が1でない: {first}"
    assert second == 0, f"2回目で重複登録された: {second}"
    assert db.query(Encounter).count() == 1
    db.close()


def test_count_partners_on():
    """当日のユニークなすれ違い人数を返す。日付範囲外は数えない。"""
    db = make_session()
    u1, u2 = setup_users(db)
    u3 = User(nickname="U3")
    db.add(u3)
    db.commit()

    today = datetime.utcnow().date()
    noon = datetime.combine(today, datetime.min.time()) + timedelta(hours=12)
    db.add_all([
        Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id, encountered_at=noon, distance_m=10.0),
        Encounter(user_id_a=u1.user_id, user_id_b=u3.user_id, encountered_at=noon, distance_m=20.0),
        # 昨日のencounterは今日のカウントに含めない
        Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id,
                  encountered_at=noon - timedelta(days=1), distance_m=10.0),
    ])
    db.commit()

    assert encounter_service.count_partners_on(db, u1.user_id, today) == 2
    assert encounter_service.count_partners_on(db, u2.user_id, today) == 1
    assert encounter_service.count_partners_on(db, u3.user_id, today) == 1
    db.close()


def test_count_partners_total():
    """全期間のユニークなすれ違い人数を返す。同じ相手と複数日すれ違っても1人と数える。"""
    db = make_session()
    u1, u2 = setup_users(db)
    u3 = User(nickname="U3")
    db.add(u3)
    db.commit()

    today = datetime.utcnow().date()
    noon = datetime.combine(today, datetime.min.time()) + timedelta(hours=12)
    db.add_all([
        # u1×u2の同一ペアで別日に2件 → ユニーク人数としては1人
        Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id, encountered_at=noon, distance_m=10.0),
        Encounter(user_id_a=u1.user_id, user_id_b=u2.user_id,
                  encountered_at=noon - timedelta(days=1), distance_m=10.0),
    ])
    db.commit()

    assert encounter_service.count_partners_total(db, u1.user_id) == 1

    # 別の相手(u3)が加わると2人になる
    db.add(Encounter(user_id_a=u1.user_id, user_id_b=u3.user_id, encountered_at=noon, distance_m=20.0))
    db.commit()

    assert encounter_service.count_partners_total(db, u1.user_id) == 2
    db.close()


if __name__ == "__main__":
    test_no_duplicate_within_single_run()
    test_no_duplicate_across_runs()
    test_count_partners_on()
    test_count_partners_total()
    print("全テスト通過")

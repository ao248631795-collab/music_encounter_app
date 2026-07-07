import math
from datetime import date, datetime, timedelta
from itertools import combinations
from sqlalchemy.orm import Session
from app.models.location import Location
from app.models.encounter import Encounter
from app.config import ENCOUNTER_DISTANCE_M, ENCOUNTER_TIME_DIFF_MINUTES


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の距離をメートルで返す（ハーバサイン公式）"""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def run_encounter_batch(db: Session) -> int:
    """
    蓄積された位置情報を突き合わせ、すれ違いペアをencountersに記録する。
    返り値: 新規登録件数
    """
    locations = db.query(Location).order_by(Location.recorded_at).all()
    time_threshold = timedelta(minutes=ENCOUNTER_TIME_DIFF_MINUTES)
    new_count = 0

    # 同一実行内の重複防止（autoflush=Falseのため、db.add()した行は
    # 下のexistingクエリに映らない。メモリ上のsetで防ぐ）
    seen: set = set()

    # ユーザーIDでグループ化
    by_user: dict[int, list[Location]] = {}
    for loc in locations:
        by_user.setdefault(loc.user_id, []).append(loc)

    user_ids = list(by_user.keys())

    for uid_a, uid_b in combinations(user_ids, 2):
        # 順序を強制（CHECK制約に合わせる）
        a, b = (uid_a, uid_b) if uid_a < uid_b else (uid_b, uid_a)

        for loc_a in by_user[a]:
            for loc_b in by_user[b]:
                if abs(loc_a.recorded_at - loc_b.recorded_at) > time_threshold:
                    continue
                dist = haversine_m(loc_a.latitude, loc_a.longitude, loc_b.latitude, loc_b.longitude)
                if dist > ENCOUNTER_DISTANCE_M:
                    continue

                # すれ違い時刻 = 2つの記録時刻の中点（日付で重複防止）
                encountered_at = _midpoint_time(loc_a.recorded_at, loc_b.recorded_at)
                encounter_date = encountered_at.date()

                # 同一実行内で同日の同一ペアを登録済みなら skip
                if (a, b, encounter_date) in seen:
                    continue

                # 同日の同一ペアが既に存在すれば skip
                existing = (
                    db.query(Encounter)
                    .filter(
                        Encounter.user_id_a == a,
                        Encounter.user_id_b == b,
                        Encounter.encountered_at >= datetime.combine(encounter_date, datetime.min.time()),
                        Encounter.encountered_at < datetime.combine(encounter_date, datetime.max.time()),
                    )
                    .first()
                )
                if existing:
                    seen.add((a, b, encounter_date))
                    continue

                db.add(Encounter(
                    user_id_a=a,
                    user_id_b=b,
                    encountered_at=encountered_at,
                    distance_m=dist,
                ))
                seen.add((a, b, encounter_date))
                new_count += 1

    db.commit()
    return new_count


def count_partners_on(db: Session, user_id: int, target_date: date) -> int:
    """target_date当日にuser_idとすれ違った相手のユニーク人数を返す。"""
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    encounters = (
        db.query(Encounter)
        .filter(
            (Encounter.user_id_a == user_id) | (Encounter.user_id_b == user_id),
            Encounter.encountered_at >= start,
            Encounter.encountered_at < end,
        )
        .all()
    )
    partners = set()
    for enc in encounters:
        partners.add(enc.user_id_b if enc.user_id_a == user_id else enc.user_id_a)
    return len(partners)


def count_partners_total(db: Session, user_id: int) -> int:
    """これまでにすれ違った相手のユニーク人数（全期間）を返す。"""
    encounters = (
        db.query(Encounter)
        .filter((Encounter.user_id_a == user_id) | (Encounter.user_id_b == user_id))
        .all()
    )
    partners = set()
    for enc in encounters:
        partners.add(enc.user_id_b if enc.user_id_a == user_id else enc.user_id_a)
    return len(partners)


def _midpoint_time(t1: datetime, t2: datetime) -> datetime:
    return t1 + (t2 - t1) / 2

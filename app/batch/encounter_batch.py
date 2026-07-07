"""
使い方: python -m app.batch.encounter_batch
"""
from app.db import SessionLocal
from app.services.encounter_service import run_encounter_batch
from app.services.location_service import delete_expired_locations


def main():
    db = SessionLocal()
    try:
        expired = delete_expired_locations(db)
        print(f"期限切れ位置情報を削除: {expired}件")
        new_encounters = run_encounter_batch(db)
        print(f"すれ違い記録を追加: {new_encounters}件")
    finally:
        db.close()


if __name__ == "__main__":
    main()

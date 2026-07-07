from sqlalchemy import inspect, text
from app.db import engine, Base
import app.models  # noqa: F401 — モデルをインポートしてBaseに登録する


def _migrate_add_spotify_refresh_token():
    """既存DBのusersにspotify_refresh_token列を一度きりで追加する（あればスキップ）。
    create_all は既存テーブルに列を追加しないため、手動ALTERで冪等に補う。"""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "spotify_refresh_token" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN spotify_refresh_token VARCHAR"))
    print("usersにspotify_refresh_token列を追加しました。")


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_add_spotify_refresh_token()
    print("テーブルを作成しました。")


if __name__ == "__main__":
    init_db()

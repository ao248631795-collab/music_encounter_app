import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.db as app_db
import app.auth as app_auth
from app.db import Base
from app.main import app


def make_client():
    """
    一時ファイルDBに差し替えたTestClientを作る（本番DBを汚さないため）。
    get_db（コントローラ）とapp.auth（ミドルウェア）の両方のSessionLocalを差し替える。
    戻り値: (client, 一時DBパス, 元のSessionLocalのタプル)
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    originals = (app_db.SessionLocal, app_auth.SessionLocal)
    app_db.SessionLocal = test_session
    app_auth.SessionLocal = test_session

    client = TestClient(app, follow_redirects=False)
    return client, path, originals


def teardown(path, originals):
    app_db.SessionLocal, app_auth.SessionLocal = originals
    try:
        os.unlink(path)
    except OSError:
        pass


def _register(client, nickname="RouteTester", password="password123"):
    return client.post("/register", data={
        "nickname": nickname, "password": password, "password_confirm": password,
    })


def test_unauthenticated_pages_redirect_to_login():
    client, path, orig = make_client()
    try:
        for p in ["/", "/songs", "/songs/search", "/locations", "/playlist",
                  "/calendar", "/calendar/monthly"]:
            r = client.get(p)
            assert r.status_code == 303, f"{p} が {r.status_code}（303であるべき）"
            assert r.headers["location"] == "/login", f"{p} のリダイレクト先が /login でない"
        # 公開ページはそのまま表示できる
        assert client.get("/login").status_code == 200
        assert client.get("/register").status_code == 200
    finally:
        teardown(path, orig)


def test_register_login_logout_flow():
    client, path, orig = make_client()
    try:
        # 登録 → 自動ログインで / へ
        r = _register(client)
        assert r.status_code == 303 and r.headers["location"] == "/"
        # 認証済みで保護ページが開ける
        assert client.get("/songs").status_code == 200
        assert client.get("/calendar").status_code == 200
        # ログアウトで再び弾かれる
        r = client.post("/logout")
        assert r.status_code == 303 and r.headers["location"] == "/login"
        assert client.get("/songs").status_code == 303
    finally:
        teardown(path, orig)


def test_login_wrong_password_rerenders():
    client, path, orig = make_client()
    try:
        _register(client)
        client.post("/logout")
        r = client.post("/login", data={"nickname": "RouteTester", "password": "wrongpass"})
        assert r.status_code == 200, "誤パスワードは再表示（200）のはず"
        assert "違います" in r.text, "エラーメッセージが表示されていない"
    finally:
        teardown(path, orig)


def test_location_bad_coords_rejected():
    client, path, orig = make_client()
    try:
        _register(client)
        # 範囲外の座標は拒否される
        r = client.post("/locations", data={"latitude": "999", "longitude": "-999"})
        assert r.status_code == 303
        assert r.headers["location"] == "/locations?error=badcoords"
        # 正常な座標は登録され、すれ違い0人のフィードバックが付く
        r = client.post("/locations", data={"latitude": "35.6580", "longitude": "139.7016"})
        assert r.status_code == 303
        assert r.headers["location"] == "/locations?registered=1&partners=0"
    finally:
        teardown(path, orig)


def test_song_post_invalid_track_id_rejected():
    client, path, orig = make_client()
    try:
        _register(client)
        r = client.post("/songs", data={
            "spotify_track_id": "<script>bad", "title": "X", "artist": "Y",
        })
        assert r.status_code == 303
        assert r.headers["location"] == "/songs/search?error=badid"
    finally:
        teardown(path, orig)


if __name__ == "__main__":
    test_unauthenticated_pages_redirect_to_login()
    test_register_login_logout_flow()
    test_login_wrong_password_rerenders()
    test_location_bad_coords_rejected()
    test_song_post_invalid_track_id_rejected()
    print("全テスト通過")

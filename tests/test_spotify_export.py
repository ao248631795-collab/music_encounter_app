import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tempfile
from datetime import date
from urllib.parse import urlparse, parse_qs

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.db as app_db
import app.auth as app_auth
from app.db import Base
import app.models  # noqa: F401 — 全モデルをBaseに登録
from app.main import app
from app.models.user import User
from app.models.daily_pick import DailyPick

from app.auth import sign_spotify_state, verify_spotify_state
from app.services import daily_pick_service
from app.services import spotify_user_client


# ---------- get_authorize_url（ネットワーク呼び出しなし） ----------

def test_authorize_url_contains_required_params():
    url = spotify_user_client.get_authorize_url("mystate.sig")
    parsed = urlparse(url)
    assert parsed.netloc == "accounts.spotify.com"
    assert parsed.path == "/authorize"
    qs = parse_qs(parsed.query)
    # client_idはconfig依存だがキーは必ず存在する
    assert "client_id" in qs
    assert qs["response_type"] == ["code"]
    assert "redirect_uri" in qs
    assert qs["scope"] == ["playlist-modify-private"]
    assert qs["state"] == ["mystate.sig"]


# ---------- state署名 往復 ----------

def test_spotify_state_roundtrip_ok():
    state = sign_spotify_state(7, 2026, 7)
    assert verify_spotify_state(state) == (7, 2026, 7)


def test_spotify_state_tampered_returns_none():
    state = sign_spotify_state(7, 2026, 7)
    payload, sig = state.rsplit(".", 1)
    # payloadのuser_idを別人に改ざん（署名は元のまま）→ None
    tampered = "999:2026:7." + sig
    assert verify_spotify_state(tampered) is None
    # 署名部の改ざんもNone
    assert verify_spotify_state(payload + ".deadbeef") is None
    # 形式不正
    assert verify_spotify_state(None) is None
    assert verify_spotify_state("no-dot") is None


def test_spotify_state_other_user_value_is_correct():
    # 別ユーザー(=42)向けに正しく署名されたstateは、その値をそのまま返す
    state = sign_spotify_state(42, 2025, 12)
    assert verify_spotify_state(state) == (42, 2025, 12)


# ---------- collect_month_track_uris（in-memory SQLite） ----------

def _make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_collect_month_track_uris():
    db = _make_session()
    u = User(nickname="U")
    db.add(u)
    db.commit()

    # track_idあり2曲（日付を逆順で登録して昇順ソートを検証）＋ track_idなし1曲
    db.add_all([
        DailyPick(user_id=u.user_id, pick_date=date(2026, 7, 20),
                  spotify_track_id="bbb", title="B", artist="artB"),
        DailyPick(user_id=u.user_id, pick_date=date(2026, 7, 5),
                  spotify_track_id="aaa", title="A", artist="artA"),
        DailyPick(user_id=u.user_id, pick_date=date(2026, 7, 10),
                  spotify_track_id=None, title="C", artist="artC", is_manual_entry=True),
    ])
    db.commit()

    uris, skipped = daily_pick_service.collect_month_track_uris(db, u.user_id, 2026, 7)
    # 日付昇順（5日 → 20日）・spotify:track: 形式
    assert uris == ["spotify:track:aaa", "spotify:track:bbb"]
    assert skipped == 1


# ---------- ルートテスト（make_clientパターン） ----------

def _make_client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    originals = (app_db.SessionLocal, app_auth.SessionLocal)
    app_db.SessionLocal = test_session
    app_auth.SessionLocal = test_session
    client = TestClient(app, follow_redirects=False)
    return client, path, originals, test_session


def _teardown(path, originals):
    app_db.SessionLocal, app_auth.SessionLocal = originals
    try:
        os.unlink(path)
    except OSError:
        pass


def _register(client, nickname="ExportTester", password="password123"):
    return client.post("/register", data={
        "nickname": nickname, "password": password, "password_confirm": password,
    })


def test_unauthenticated_connect_redirects_to_login():
    client, path, orig, _ = _make_client()
    try:
        r = client.get("/spotify/connect?year=2026&month=7")
        assert r.status_code == 303
        assert r.headers["location"] == "/login"
    finally:
        _teardown(path, orig)


def test_export_no_tracks_redirects_notracks():
    client, path, orig, _ = _make_client()
    try:
        _register(client)  # ピックが1件もないユーザー
        r = client.post("/spotify/export", data={"year": 2026, "month": 7})
        assert r.status_code == 303
        assert "export=notracks" in r.headers["location"]
    finally:
        _teardown(path, orig)


def test_export_with_tracks_unconnected_redirects_to_connect():
    client, path, orig, session = _make_client()
    try:
        _register(client)
        # 登録したユーザーにtrack_id付きのピックを1件足す（未連携のまま）
        db = session()
        user = db.query(User).first()
        db.add(DailyPick(user_id=user.user_id, pick_date=date(2026, 7, 3),
                         spotify_track_id="zzz", title="Z", artist="artZ"))
        db.commit()
        db.close()

        r = client.post("/spotify/export", data={"year": 2026, "month": 7})
        assert r.status_code == 303
        assert "/spotify/connect" in r.headers["location"]
        assert "year=2026" in r.headers["location"]
        assert "month=7" in r.headers["location"]
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    test_authorize_url_contains_required_params()
    test_spotify_state_roundtrip_ok()
    test_spotify_state_tampered_returns_none()
    test_spotify_state_other_user_value_is_correct()
    test_collect_month_track_uris()
    test_unauthenticated_connect_redirects_to_login()
    test_export_no_tracks_redirects_notracks()
    test_export_with_tracks_unconnected_redirects_to_connect()
    print("全テスト通過")

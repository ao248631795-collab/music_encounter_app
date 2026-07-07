from dotenv import load_dotenv
import os

load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
# ユーザーOAuth認可のリダイレクト先（Spotify Dashboardに登録した値と一致させる）
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/spotify/callback")

# セッションCookie署名用。開発用デフォルトを固定値にして--reloadでセッションが切れないようにする
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

DATABASE_URL = "sqlite:///./music_encounter.db"

ENCOUNTER_DISTANCE_M = 100.0
ENCOUNTER_TIME_DIFF_MINUTES = 30
LOCATION_EXPIRE_HOURS = 24
SONG_MAX_PER_USER = 5
SPOTIFY_SEARCH_TIMEOUT_SEC = 5.0

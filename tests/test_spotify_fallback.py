import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
import httpx
from app.services.spotify_client import search_tracks, SpotifySearchError


def _mock_token():
    return "dummy_token"


def test_fallback_on_timeout():
    with patch("app.services.spotify_client.get_token", return_value="tok"), \
         patch("httpx.get", side_effect=httpx.TimeoutException("timeout")):
        try:
            search_tracks("test")
            assert False, "例外が発生するはずです"
        except SpotifySearchError:
            pass


def test_fallback_on_http_error():
    mock_resp = httpx.Response(500, request=httpx.Request("GET", "https://api.spotify.com"))
    with patch("app.services.spotify_client.get_token", return_value="tok"), \
         patch("httpx.get", return_value=mock_resp):
        try:
            search_tracks("test")
            assert False, "例外が発生するはずです"
        except SpotifySearchError:
            pass


def test_empty_results():
    mock_resp = httpx.Response(
        200,
        json={"tracks": {"items": []}},
        request=httpx.Request("GET", "https://api.spotify.com"),
    )
    with patch("app.services.spotify_client.get_token", return_value="tok"), \
         patch("httpx.get", return_value=mock_resp):
        results = search_tracks("xyznotexist")
        assert results == []


if __name__ == "__main__":
    test_fallback_on_timeout()
    test_fallback_on_http_error()
    test_empty_results()
    print("全テスト通過")

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.encounter_service import haversine_m


def test_same_point():
    assert haversine_m(35.0, 139.0, 35.0, 139.0) == 0.0


def test_known_distance():
    # 渋谷〜新宿 約 2.3km
    dist = haversine_m(35.6580, 139.7016, 35.6938, 139.7034)
    assert 2000 < dist < 4500, f"想定外の距離: {dist:.0f}m"


def test_100m_threshold():
    # 約0.001度 ≒ 111m
    dist = haversine_m(35.0, 139.0, 35.001, 139.0)
    assert 100 < dist < 130, f"想定外の距離: {dist:.0f}m"


if __name__ == "__main__":
    test_same_point()
    test_known_distance()
    test_100m_threshold()
    print("全テスト通過")

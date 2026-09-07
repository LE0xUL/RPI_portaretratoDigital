from datetime import datetime

from app.schedule import compute_screen_on


def test_disabled_schedule_always_on():
    assert compute_screen_on(False, "22:00", "07:00", datetime(2026, 1, 1, 3, 0)) is True


def test_window_within_same_day():
    # apagado 13:00 -> 15:00
    assert compute_screen_on(True, "15:00", "13:00", datetime(2026, 1, 1, 14, 0)) is False
    assert compute_screen_on(True, "15:00", "13:00", datetime(2026, 1, 1, 16, 0)) is True
    assert compute_screen_on(True, "15:00", "13:00", datetime(2026, 1, 1, 10, 0)) is True


def test_window_crossing_midnight():
    # apagado 22:00 -> 07:00
    assert compute_screen_on(True, "07:00", "22:00", datetime(2026, 1, 1, 23, 30)) is False
    assert compute_screen_on(True, "07:00", "22:00", datetime(2026, 1, 2, 3, 0)) is False
    assert compute_screen_on(True, "07:00", "22:00", datetime(2026, 1, 2, 7, 0)) is True
    assert compute_screen_on(True, "07:00", "22:00", datetime(2026, 1, 1, 12, 0)) is True

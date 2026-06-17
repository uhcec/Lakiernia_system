from datetime import date

from app.manager.service import _format_period_label, _parse_period_start


# NA7 — weekly throughput periods use one consistent ISO convention end-to-end.
# Grouping is strftime("%G-%V") (ISO year + ISO week); parsing is date.fromisocalendar,
# so period starts land on the ISO Monday and stay correct across year boundaries.


def test_week_period_start_is_iso_monday() -> None:
    # ISO week 25 of 2026 starts Monday 2026-06-15.
    assert _parse_period_start("2026-25", "week") == date(2026, 6, 15)


def test_week_period_start_handles_year_boundaries() -> None:
    # 2025-12-29 (Mon) is ISO 2026-W01; 2026-12-28 (Mon) is ISO 2026-W53.
    assert _parse_period_start("2026-01", "week") == date(2025, 12, 29)
    assert _parse_period_start("2026-53", "week") == date(2026, 12, 28)


def test_week_period_label_matches_iso_week_number() -> None:
    assert _format_period_label("2026-01", "week") == "Tydzień 1, 2026"
    assert _format_period_label("2026-25", "week") == "Tydzień 25, 2026"


def test_day_and_month_periods_unchanged() -> None:
    assert _parse_period_start("2026-06-15", "day") == date(2026, 6, 15)
    assert _parse_period_start("2026-06", "month") == date(2026, 6, 1)
    assert _format_period_label("2026-06", "month") == "Czerwiec 2026"

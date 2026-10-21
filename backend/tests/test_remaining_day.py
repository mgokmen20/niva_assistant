"""Remaining-hour forecast. Morning rain is ignored after noon."""

from app.services.weather_service import format_remaining_day, summarize_remaining_hours


def test_afternoon_request_ignores_morning_rain() -> None:
    """A wet 09:00 does not raise the rain chance once the hour is 12."""
    summary = summarize_remaining_hours(
        {
            "current": {"time": "2026-10-21T12:00", "temperature_2m": 14.0},
            "hourly": {
                "time": [
                    "2026-10-21T09:00",
                    "2026-10-21T12:00",
                    "2026-10-21T18:00",
                ],
                "temperature_2m": [9.0, 14.0, 18.0],
                "precipitation_probability": [80, 5, 10],
            },
        }
    )

    assert summary is not None
    assert summary["min_temp"] == 14.0
    assert summary["max_temp"] == 18.0
    assert summary["precipitation_probability"] == 10
    assert summary["rain_hour"] is None
    assert format_remaining_day(summary) == "Currently 14°C, reaching 18°C at 18:00"


def test_evening_rain_is_kept_when_it_is_still_ahead() -> None:
    """Rain later today stays in the summary and the briefing."""
    summary = summarize_remaining_hours(
        {
            "current": {"time": "2026-10-21T10:00", "temperature_2m": 10.0},
            "hourly": {
                "time": ["2026-10-21T09:00", "2026-10-21T10:00", "2026-10-21T12:00", "2026-10-21T18:00"],
                "temperature_2m": [8.0, 10.0, 18.0, 16.0],
                "precipitation_probability": [90, 10, 5, 60],
            },
        }
    )

    assert summary is not None
    assert summary["precipitation_probability"] == 60
    assert summary["rain_hour"] == 18
    assert summary["min_temp"] == 10.0
    assert format_remaining_day(summary) == "Currently 10°C, reaching 18°C at noon, rain expected at 18:00"

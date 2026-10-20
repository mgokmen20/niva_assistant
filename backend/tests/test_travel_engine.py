"""Packing rules and travel summaries. No test contacts the network."""

from datetime import date

import pytest

from app.core.config import Settings
from app.core.constants import PREFERRED_LANGUAGE_DE, PREFERRED_LANGUAGE_TR
from app.services.travel_engine import (
    ITEM_BASE_SHIRT,
    ITEM_FLEECE,
    ITEM_LIGHT_JACKET,
    ITEM_SUNGLASSES,
    ITEM_UMBRELLA,
    ITEM_WATERPROOF_SHELL,
    ITEM_WINTER_COAT,
    TravelWindowError,
    TripDay,
    compose_travel_summary,
    plan_packing,
    validate_trip_window,
)


def _day(
    day: str,
    low: float,
    high: float,
    rain: float = 0.0,
    code: int = 3,
    uv: float | None = 1.0,
) -> TripDay:
    return TripDay(day, low, high, rain, code, uv)


def _ids(days: list[TripDay]) -> dict[str, int]:
    return {item.item_id: item.quantity for item in plan_packing(days)}


def test_four_mild_days_scale_base_shirts_only() -> None:
    """A warm dry span packs one shirt per day and nothing else."""
    packed = _ids([_day(f"2026-10-{19 + offset}", 20.0, 26.0, code=3, uv=1.0) for offset in range(4)])
    assert packed == {ITEM_BASE_SHIRT: 4}


def test_cold_wet_clear_span_adds_layers() -> None:
    """Night frost, a 10 °C day, rain, and sun each add their own item."""
    packed = _ids(
        [
            _day("2026-10-19", 3.0, 8.0, rain=10, code=3, uv=1.0),
            _day("2026-10-20", 10.0, 14.0, rain=40, code=61, uv=1.0),
            _day("2026-10-21", 16.0, 22.0, rain=0, code=0, uv=1.0),
            _day("2026-10-22", 18.0, 24.0, rain=0, code=2, uv=4.0),
        ]
    )
    assert packed[ITEM_BASE_SHIRT] == 4
    assert packed[ITEM_FLEECE] == 1
    assert packed[ITEM_WINTER_COAT] == 1
    assert packed[ITEM_LIGHT_JACKET] == 1
    assert packed[ITEM_WATERPROOF_SHELL] == 1
    assert packed[ITEM_UMBRELLA] == 1
    assert packed[ITEM_SUNGLASSES] == 1


def test_freezing_day_without_a_mild_afternoon_skips_the_light_jacket() -> None:
    """A day that never reaches 5 °C is a coat day, not a light-jacket day."""
    packed = _ids([_day("2026-10-19", -2.0, 4.0, code=71, uv=0.2)])
    assert ITEM_WINTER_COAT in packed
    assert ITEM_FLEECE in packed
    assert ITEM_LIGHT_JACKET not in packed


def test_rain_at_thirty_percent_includes_shell_and_umbrella() -> None:
    """Travel rain uses 30 percent, which is below the daily umbrella cut."""
    packed = _ids([_day("2026-10-19", 20.0, 24.0, rain=30, code=3, uv=1.0)])
    assert packed[ITEM_UMBRELLA] == 1
    assert packed[ITEM_WATERPROOF_SHELL] == 1


def test_trip_window_rejects_a_reversed_or_long_span() -> None:
    today = date(2026, 10, 19)
    with pytest.raises(TravelWindowError) as reversed_window:
        validate_trip_window(date(2026, 10, 22), date(2026, 10, 19), today)
    assert reversed_window.value.code == "end_before_start"
    with pytest.raises(TravelWindowError) as long_window:
        validate_trip_window(today, date(2026, 11, 10), today)
    assert long_window.value.code == "too_long"


@pytest.mark.asyncio
async def test_german_summary_falls_back_without_credentials() -> None:
    """An empty Cloudflare account keeps the Swiss fallback and drops ß."""
    settings = Settings(CLOUDFLARE_ACCOUNT_ID="", CLOUDFLARE_API_TOKEN="", SECRET_KEY="test", _env_file=None)
    days = [_day("2026-10-19", 4.0, 9.0, rain=35, code=1, uv=1.0)]
    items = plan_packing(days)
    summary = await compose_travel_summary(
        city_name="Bern",
        language=PREFERRED_LANGUAGE_DE,
        items=items,
        days=days,
        settings=settings,
    )
    assert "Basis-Shirts" in summary
    assert "leichte Jacke" in summary
    assert "ß" not in summary
    assert not summary.startswith("Pack ")


@pytest.mark.asyncio
async def test_turkish_summary_uses_the_model_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Turkish Workers AI reply replaces the local fallback."""

    async def reply(**_kwargs: object) -> str:
        return "Bern için valize tişört ve mont koyun. Yağmur olasılığı yüksek."

    monkeypatch.setattr("app.services.travel_engine.request_outfit_summary", reply)
    settings = Settings(CLOUDFLARE_ACCOUNT_ID="account", CLOUDFLARE_API_TOKEN="token", SECRET_KEY="test", _env_file=None)
    days = [_day("2026-10-19", 8.0, 12.0)]
    summary = await compose_travel_summary(
        city_name="Bern",
        language=PREFERRED_LANGUAGE_TR,
        items=plan_packing(days),
        days=days,
        settings=settings,
    )
    assert "tişört" in summary
    assert "valize" in summary

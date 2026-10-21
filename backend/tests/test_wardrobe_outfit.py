"""Hybrid wardrobe pool: temperature filter, fallbacks, and a failed stylist."""

import random
from dataclasses import dataclass

from app.core.constants import (
    EXTRA_RAINCOAT_NAME,
    EXTRA_SUNGLASSES_NAME,
    EXTRA_SUNSCREEN_NAME,
    EXTRA_UMBRELLA_NAME,
    STANDARD_CASUAL_PANTS_NAME,
    STANDARD_CASUAL_SHORTS_NAME,
    STANDARD_LIGHT_JACKET_NAME,
    STANDARD_TSHIRT_NAME,
    STANDARD_WARM_SWEATER_NAME,
    STANDARD_WINTER_COAT_NAME,
)
from app.services.wardrobe_outfit import (
    PLAN_COLD_PAIR,
    PLAN_REMOVABLE,
    ROLE_BOTTOM,
    ROLE_OUTERWEAR,
    ROLE_TOP,
    assign_outfit,
    build_hybrid_pool,
    choose_fallback_outfit,
    complete_selection,
    layer_plan,
    layers_from_selection,
)


@dataclass(frozen=True, slots=True)
class _Garment:
    """One owned garment for the pool builder."""

    item_name: str
    category: str
    thickness: str = "Normal"
    color_name: str = "Navy"
    style: str = "Casual"
    is_waterproof: bool = False


def _names(pool_items: object) -> set[str]:
    """Collect display names from a pool or a selection."""
    return {item.name for item in pool_items}  # type: ignore[attr-defined]


def test_cold_empty_wardrobe_injects_a_sweater_pants_and_a_coat() -> None:
    """Below freezing, a missing wardrobe still yields a complete cold outfit."""
    pool = build_hybrid_pool(
        [],
        effective_temperature_celsius=2.0,
        wind_speed_mps=1.0,
        rain_probability_percent=0.0,
        uv_index=1.0,
        weather_code=0,
    )

    assert pool.outerwear_required is True
    assert _names(pool.items) == {
        STANDARD_WARM_SWEATER_NAME,
        STANDARD_CASUAL_PANTS_NAME,
        STANDARD_WINTER_COAT_NAME,
    }


def test_shorts_and_thin_items_are_removed_below_ten_degrees() -> None:
    """A chilly day keeps a sweater and pants and drops shorts and thin cloth."""
    pool = build_hybrid_pool(
        [
            _Garment("Linen Tee", "T-Shirt", thickness="Thin"),
            _Garment("Denim Shorts", "Shorts", thickness="Normal"),
            _Garment("Wool Sweater", "Sweater", thickness="Thick"),
            _Garment("Chinos", "Pants", thickness="Normal"),
        ],
        effective_temperature_celsius=8.0,
        wind_speed_mps=1.0,
        rain_probability_percent=0.0,
        uv_index=1.0,
        weather_code=0,
    )

    names = _names(pool.items)
    assert "Linen Tee" not in names
    assert "Denim Shorts" not in names
    assert "Wool Sweater" in names
    assert "Chinos" in names
    assert STANDARD_LIGHT_JACKET_NAME in names
    assert STANDARD_WARM_SWEATER_NAME not in names


def test_rain_above_forty_and_high_uv_add_extras() -> None:
    """Rain above 40 percent and UV 5 add the environmental items."""
    pool = build_hybrid_pool(
        [],
        effective_temperature_celsius=16.0,
        wind_speed_mps=1.0,
        rain_probability_percent=41.0,
        uv_index=5.0,
        weather_code=0,
    )

    names = _names(pool.items)
    assert EXTRA_UMBRELLA_NAME in names
    assert EXTRA_RAINCOAT_NAME in names
    assert EXTRA_SUNGLASSES_NAME in names
    assert EXTRA_SUNSCREEN_NAME in names


def test_rain_at_forty_does_not_add_the_umbrella_extra() -> None:
    """Exactly 40 percent stays under the wardrobe rain-extra cut."""
    pool = build_hybrid_pool(
        [],
        effective_temperature_celsius=19.0,
        wind_speed_mps=1.0,
        rain_probability_percent=40.0,
        uv_index=2.6,
        weather_code=0,
    )

    names = _names(pool.items)
    assert EXTRA_UMBRELLA_NAME not in names
    assert EXTRA_RAINCOAT_NAME not in names
    assert STANDARD_LIGHT_JACKET_NAME in names


def test_hot_clear_day_uses_shorts_and_sun_items_without_a_coat() -> None:
    """A hot day needs a top and shorts, plus sun extras, and no outer layer."""
    pool = build_hybrid_pool(
        [],
        effective_temperature_celsius=26.0,
        wind_speed_mps=1.0,
        rain_probability_percent=0.0,
        uv_index=2.0,
        weather_code=0,
    )

    assert pool.outerwear_required is False
    names = _names(pool.items)
    assert STANDARD_TSHIRT_NAME in names
    assert STANDARD_CASUAL_SHORTS_NAME in names
    assert STANDARD_LIGHT_JACKET_NAME not in names
    assert EXTRA_SUNGLASSES_NAME in names
    assert EXTRA_SUNSCREEN_NAME in names


def test_failed_stylist_picks_one_item_for_each_required_role() -> None:
    """A parse failure still returns one top, one bottom, and one outer layer."""
    pool = build_hybrid_pool(
        [
            _Garment("Navy Sweater", "Sweater"),
            _Garment("Grey Sweater", "Sweater"),
            _Garment("Chinos", "Pants"),
            _Garment("Wool Trousers", "Pants"),
            _Garment("Parka", "Outerwear"),
        ],
        effective_temperature_celsius=8.0,
        wind_speed_mps=1.0,
        rain_probability_percent=0.0,
        uv_index=1.0,
        weather_code=0,
    )
    selected = choose_fallback_outfit(pool, random.Random(3))
    roles = [item.role for item in selected]

    assert roles.count(ROLE_TOP) == 1
    assert roles.count(ROLE_BOTTOM) == 1
    assert roles.count(ROLE_OUTERWEAR) == 1


def test_partial_json_fills_the_missing_bottom() -> None:
    """A reply that names only the top still receives a bottom and a coat."""
    pool = build_hybrid_pool(
        [
            _Garment("Navy Sweater", "Sweater"),
            _Garment("Chinos", "Pants"),
            _Garment("Parka", "Outerwear"),
        ],
        effective_temperature_celsius=8.0,
        wind_speed_mps=1.0,
        rain_probability_percent=0.0,
        uv_index=1.0,
        weather_code=0,
    )
    selected = complete_selection(pool, ["Navy Sweater"], random.Random(1))
    names = _names(selected)

    assert "Navy Sweater" in names
    assert "Chinos" in names
    assert "Parka" in names


def test_high_variance_adds_a_shirt_a_removable_sweater_and_one_coat() -> None:
    """A day that swings from cold to warm keeps three upper-body pieces."""
    assert layer_plan(6.0, 20.0) == PLAN_REMOVABLE
    pool = build_hybrid_pool(
        [],
        effective_temperature_celsius=8.0,
        wind_speed_mps=1.0,
        rain_probability_percent=0.0,
        uv_index=1.0,
        weather_code=0,
        min_temperature_celsius=6.0,
        max_temperature_celsius=20.0,
    )
    selected = assign_outfit(pool, None, random.Random(1))
    payload = layers_from_selection(selected, pool.layer_plan)
    tops = payload["tops"]

    assert isinstance(tops, list)
    assert [item["label"] for item in tops] == ["Standard T-Shirt", "Standard Warm Sweater"]
    assert tops[1]["removable"] is True
    assert payload["outerwear"]["label"] == "Standard Light Jacket"
    assert payload["bottom"]["category"] == "BOTTOM"
    assert sum(1 for item in selected if item.role == ROLE_OUTERWEAR) == 1


def test_a_cold_day_with_low_variance_does_not_add_a_third_layer() -> None:
    """A day that stays cold is a sweater and one coat."""
    assert layer_plan(2.0, 8.0) == PLAN_COLD_PAIR
    pool = build_hybrid_pool(
        [_Garment("Linen Tee", "T-Shirt", thickness="Normal")],
        effective_temperature_celsius=4.0,
        wind_speed_mps=1.0,
        rain_probability_percent=0.0,
        uv_index=1.0,
        weather_code=0,
        min_temperature_celsius=2.0,
        max_temperature_celsius=8.0,
    )
    selected = assign_outfit(pool, None, random.Random(1))
    labels = [item.name for item in selected if item.role == ROLE_TOP]

    assert labels == ["Standard Warm Sweater"]
    assert "Linen Tee" not in labels
    assert sum(1 for item in selected if item.role == ROLE_OUTERWEAR) == 1

"""Unit tests for the pure thermal decision engine.

The named cases lock the age offsets, the personal comfort shift, warm-weather
dress, rain protection, and the pediatric UV / removable-mid-layer rules.
Later tests cover UTCI edges and feedback clamping.
"""

import ast
import math
from pathlib import Path
from typing import Final

import pytest

from app.core.constants import (
    CARDIGAN,
    CHILD_COLD_OFFSET_CELSIUS,
    CHILD_UV_PROTECTION_MIN_INDEX,
    FEEDBACK_MAX_OFFSET,
    FEEDBACK_MIN_OFFSET,
    FLEECE_MID_LAYER,
    GLOVES,
    INSULATED_MID_LAYER,
    LIGHT_JACKET,
    LIGHT_T_SHIRT,
    LONG_SLEEVE_BASE,
    SCARF,
    SENIOR_COLD_OFFSET_CELSIUS,
    SUNGLASSES,
    THERMAL_BASE_LAYER,
    UMBRELLA,
    UV_PROTECTION_MIN_INDEX,
    WARM_HAT,
    WATERPROOF_SHELL,
    WIND_SHELL,
    WINTER_COAT,
    ZIP_HOODIE,
    ThermalStressCategory,
)
from app.domain.thermal_engine import (
    ClothingRecommendation,
    ThermalInput,
    calculate_effective_temperature,
    classify_utci_stress,
    determine_clothing_layers,
)

ADULT_AGE_YEARS: Final[int] = 30
SENIOR_AGE_YEARS: Final[int] = 70
CHILD_AGE_YEARS: Final[int] = 8
REFERENCE_FEELS_LIKE_C: Final[float] = 16.0
PERSONAL_OFFSET_C: Final[float] = 1.5
WARM_EFFECTIVE_TEMP_C: Final[float] = 25.0
SUNNY_UV_INDEX: Final[float] = 6.0
RAINY_EFFECTIVE_TEMP_C: Final[float] = 15.0
RAIN_PROBABILITY_PERCENT: Final[float] = 70.0
WIND_SPEED_KMH: Final[float] = 30.0
KILOMETRES_PER_HOUR_TO_METRES_PER_SECOND: Final[float] = 3.6
CHILD_SLIGHT_COLD_C: Final[float] = 5.0
CHILD_UV_INDEX: Final[float] = 2.6
HEAVY_OUTER_IDS: Final[frozenset[str]] = frozenset(
    {WINTER_COAT.id, WATERPROOF_SHELL.id}
)
RAIN_PROTECTION_IDS: Final[frozenset[str]] = frozenset(
    {WATERPROOF_SHELL.id, UMBRELLA.id}
)


def _kilometres_per_hour_to_metres_per_second(speed_kmh: float) -> float:
    """Convert a forecast wind speed into the engine's metres-per-second unit."""
    return speed_kmh / KILOMETRES_PER_HOUR_TO_METRES_PER_SECOND


def _accessory_ids(result: ClothingRecommendation) -> set[str]:
    """Return the ids of every recommended accessory."""
    return {item["id"] for item in result["accessories"]}


def _outer_id(result: ClothingRecommendation) -> str | None:
    """Return the outer garment id, or None when that slot is empty."""
    outer_layer = result["outer_layer"]
    if outer_layer is None:
        return None
    return outer_layer["id"]


def _selected_ids(result: ClothingRecommendation) -> set[str]:
    """Return outer and accessory ids that count as worn or carried items."""
    selected = _accessory_ids(result)
    outer_id = _outer_id(result)
    if outer_id is not None:
        selected.add(outer_id)
    return selected


def test_calculate_effective_temperature_adult() -> None:
    """A standard adult with no personal offset keeps the feels-like temperature.

    Ages from 12 through 64 have no pediatric or geriatric cold shift, so
    with a zero comfort offset the effective temperature equals feels-like.
    """
    effective = calculate_effective_temperature(
        feels_like=REFERENCE_FEELS_LIKE_C,
        age=ADULT_AGE_YEARS,
        personal_offset=0.0,
    )
    assert effective == REFERENCE_FEELS_LIKE_C


def test_calculate_effective_temperature_senior() -> None:
    """A senior with no personal offset is treated as 2.0 °C colder.

    From age 65 the engine subtracts the senior cold offset, representing
    blunted cold perception and weaker vasoconstriction.
    """
    effective = calculate_effective_temperature(
        feels_like=REFERENCE_FEELS_LIKE_C,
        age=SENIOR_AGE_YEARS,
        personal_offset=0.0,
    )
    assert effective == REFERENCE_FEELS_LIKE_C - SENIOR_COLD_OFFSET_CELSIUS
    assert SENIOR_COLD_OFFSET_CELSIUS == 2.0


def test_calculate_effective_temperature_child() -> None:
    """A child with no personal offset is treated as 1.0 °C colder.

    Under age 12 the engine subtracts the child cold offset, representing
    faster heat loss from a higher surface-area-to-mass ratio.
    """
    effective = calculate_effective_temperature(
        feels_like=REFERENCE_FEELS_LIKE_C,
        age=CHILD_AGE_YEARS,
        personal_offset=0.0,
    )
    assert effective == REFERENCE_FEELS_LIKE_C - CHILD_COLD_OFFSET_CELSIUS
    assert CHILD_COLD_OFFSET_CELSIUS == 1.0


def test_calculate_effective_temperature_personal_offset() -> None:
    """A positive comfort offset raises effective temperature by that amount.

    ASHRAE 55 treats comfort as an individual preference. For a standard
    adult the age offset is zero, so +1.5 °C is added directly to feels-like.
    """
    effective = calculate_effective_temperature(
        feels_like=REFERENCE_FEELS_LIKE_C,
        age=ADULT_AGE_YEARS,
        personal_offset=PERSONAL_OFFSET_C,
    )
    assert effective == REFERENCE_FEELS_LIKE_C + PERSONAL_OFFSET_C


def test_chilly_band_never_drops_the_mid_or_outer_layer() -> None:
    """10.3°C is chilly: long sleeves, fleece, and a jacket are all required."""
    result = determine_clothing_layers(
        effective_temp=10.3,
        wind_speed=1.0,
        rain_prob=10.0,
        uv_index=1.0,
        age=ADULT_AGE_YEARS,
    )

    assert result["base_layer"]["id"] == LONG_SLEEVE_BASE.id
    assert result["mid_layer"] is not None
    assert result["mid_layer"]["id"] == FLEECE_MID_LAYER.id
    assert result["outer_layer"] is not None
    assert result["outer_layer"]["id"] == LIGHT_JACKET.id


def test_clothing_bands_follow_the_european_temperature_cuts() -> None:
    """Freezing, mild, warm, and hot bands pick the layers named for each cut."""
    freezing = determine_clothing_layers(-1.0, 0.0, 0.0, 0.0, age=ADULT_AGE_YEARS)
    mild = determine_clothing_layers(15.0, 0.0, 0.0, 0.0, age=ADULT_AGE_YEARS)
    warm = determine_clothing_layers(20.0, 0.0, 0.0, 1.0, age=ADULT_AGE_YEARS)
    hot = determine_clothing_layers(24.0, 0.0, 0.0, 1.0, age=ADULT_AGE_YEARS)
    warm_and_windy = determine_clothing_layers(20.0, 6.0, 0.0, 1.0, age=ADULT_AGE_YEARS)

    assert freezing["base_layer"]["id"] == THERMAL_BASE_LAYER.id
    assert freezing["mid_layer"] is not None
    assert freezing["mid_layer"]["id"] == INSULATED_MID_LAYER.id
    assert freezing["outer_layer"]["id"] == WINTER_COAT.id
    assert {item["id"] for item in freezing["accessories"]} >= {WARM_HAT.id, SCARF.id, GLOVES.id}
    assert mild["base_layer"]["id"] == LIGHT_T_SHIRT.id
    assert mild["outer_layer"]["id"] == LIGHT_JACKET.id
    assert warm["mid_layer"] is None
    assert warm["outer_layer"] is None
    assert warm_and_windy["outer_layer"] is not None
    assert warm_and_windy["outer_layer"]["id"] == WIND_SHELL.id
    assert hot["base_layer"]["id"] == LIGHT_T_SHIRT.id
    assert hot["mid_layer"] is None
    assert hot["outer_layer"] is None
    assert SUNGLASSES.id in {item["id"] for item in hot["accessories"]}


def test_calibration_offset_changes_the_band_before_layers_are_chosen() -> None:
    """A colder personal offset moves 14°C from a mild outfit into the chilly one."""
    balanced = determine_clothing_layers(
        calculate_effective_temperature(14.0, personal_offset=0.0, age=ADULT_AGE_YEARS),
        wind_speed=0.0,
        rain_prob=0.0,
        uv_index=0.0,
        age=ADULT_AGE_YEARS,
    )
    colder = determine_clothing_layers(
        calculate_effective_temperature(14.0, personal_offset=-2.0, age=ADULT_AGE_YEARS),
        wind_speed=0.0,
        rain_prob=0.0,
        uv_index=0.0,
        age=ADULT_AGE_YEARS,
    )

    assert balanced["base_layer"]["id"] == LIGHT_T_SHIRT.id
    assert balanced["mid_layer"] is None
    assert colder["base_layer"]["id"] == LONG_SLEEVE_BASE.id
    assert colder["mid_layer"] is not None
    assert colder["mid_layer"]["id"] == FLEECE_MID_LAYER.id
    assert colder["outer_layer"] is not None
    assert colder["outer_layer"]["id"] == LIGHT_JACKET.id


def test_clothing_layers_warm_weather() -> None:
    """Sunny 25 °C selects a light base layer and no heavy outer coat.

    25 °C is in the hot clothing band. Calm wind and no rain leave the
    outer slot empty; a high UV index adds sun protection.
    """
    result = determine_clothing_layers(
        effective_temp=WARM_EFFECTIVE_TEMP_C,
        wind_speed=0.0,
        rain_prob=0.0,
        uv_index=SUNNY_UV_INDEX,
        age=ADULT_AGE_YEARS,
    )
    assert result["base_layer"]["id"] == LIGHT_T_SHIRT.id
    assert result["base_layer"]["category"] == "BASE"
    assert _outer_id(result) not in HEAVY_OUTER_IDS
    assert _outer_id(result) is None


def test_clothing_layers_rain_and_wind() -> None:
    """Rain at 70 percent with a 30 km/h wind includes rain protection.

    The engine reads wind in metres per second, so 30 km/h is converted
    before the call. Rain probability is above the 50 percent umbrella
    threshold, and on a mild day that also selects a waterproof shell.
    """
    result = determine_clothing_layers(
        effective_temp=RAINY_EFFECTIVE_TEMP_C,
        wind_speed=_kilometres_per_hour_to_metres_per_second(WIND_SPEED_KMH),
        rain_prob=RAIN_PROBABILITY_PERCENT,
        uv_index=1.0,
        age=ADULT_AGE_YEARS,
    )
    assert _selected_ids(result) & RAIN_PROTECTION_IDS


def test_child_uv_and_removable_layer() -> None:
    """A child at UV 2.6 gets sun protection and a removable mid layer.

    Pediatric sun protection starts at UV 2.5, below the adult threshold
    of 3.0. The temperature is slight cold (5 °C), where a child receives
    a cardigan or zip hoodie that can be taken off when activity or a
    warm room reverses heat loss.
    """
    result = determine_clothing_layers(
        effective_temp=CHILD_SLIGHT_COLD_C,
        wind_speed=0.0,
        rain_prob=0.0,
        uv_index=CHILD_UV_INDEX,
        age=CHILD_AGE_YEARS,
    )
    mid_layer = result["mid_layer"]
    assert CHILD_UV_INDEX >= CHILD_UV_PROTECTION_MIN_INDEX
    assert CHILD_UV_INDEX < UV_PROTECTION_MIN_INDEX
    assert SUNGLASSES.id in _accessory_ids(result)
    assert mid_layer is not None
    assert mid_layer["removable"] is True
    assert mid_layer["category"] == "MID"
    assert mid_layer["id"] in {CARDIGAN.id, ZIP_HOODIE.id}


def test_effective_temperature_clamps_feedback_bounds() -> None:
    """Personal offsets outside [-5.0, +5.0] are clamped before the formula."""
    assert calculate_effective_temperature(
        feels_like=0.0,
        age=ADULT_AGE_YEARS,
        personal_offset=FEEDBACK_MAX_OFFSET,
    ) == FEEDBACK_MAX_OFFSET
    assert calculate_effective_temperature(
        feels_like=0.0,
        age=ADULT_AGE_YEARS,
        personal_offset=FEEDBACK_MIN_OFFSET,
    ) == FEEDBACK_MIN_OFFSET
    assert calculate_effective_temperature(
        feels_like=0.0,
        age=ADULT_AGE_YEARS,
        personal_offset=9.0,
    ) == FEEDBACK_MAX_OFFSET
    assert calculate_effective_temperature(
        feels_like=0.0,
        age=ADULT_AGE_YEARS,
        personal_offset=-9.0,
    ) == FEEDBACK_MIN_OFFSET


def test_age_offsets_change_on_the_child_and_senior_thresholds() -> None:
    """Age 11 is a child, age 12 is not, age 64 is an adult, and age 65 is a senior."""
    feels_like = 10.0
    assert calculate_effective_temperature(feels_like, 11, 0.0) == 9.0
    assert calculate_effective_temperature(feels_like, 12, 0.0) == 10.0
    assert calculate_effective_temperature(feels_like, 64, 0.0) == 10.0
    assert calculate_effective_temperature(feels_like, 65, 0.0) == 8.0


@pytest.mark.parametrize(
    ("effective_temp", "category"),
    [
        (32.1, ThermalStressCategory.EXTREME_HEAT),
        (32.0, ThermalStressCategory.MODERATE_HEAT),
        (26.1, ThermalStressCategory.MODERATE_HEAT),
        (26.0, ThermalStressCategory.COMFORT),
        (9.0, ThermalStressCategory.COMFORT),
        (8.9, ThermalStressCategory.SLIGHT_COLD),
        (0.0, ThermalStressCategory.SLIGHT_COLD),
        (-0.1, ThermalStressCategory.MODERATE_COLD),
        (-13.0, ThermalStressCategory.MODERATE_COLD),
        (-13.1, ThermalStressCategory.EXTREME_COLD),
    ],
)
def test_utci_band_boundaries(
    effective_temp: float,
    category: ThermalStressCategory,
) -> None:
    """Shared UTCI edges belong to the warmer band; extremes use strict cuts."""
    assert classify_utci_stress(effective_temp) is category


def test_extreme_cold_keeps_a_required_mid_layer_for_adults() -> None:
    """Adult extreme cold keeps an insulating mid layer that is not removable."""
    result = determine_clothing_layers(
        effective_temp=-20.0,
        wind_speed=1.0,
        rain_prob=50.0,
        uv_index=0.0,
        age=ADULT_AGE_YEARS,
    )
    mid_layer = result["mid_layer"]
    assert result["base_layer"]["id"] == "thermal_base_layer"
    assert mid_layer is not None
    assert mid_layer["removable"] is False
    assert _outer_id(result) == WINTER_COAT.id
    assert UMBRELLA.id in _accessory_ids(result)


def test_thermal_input_rejects_impossible_observations() -> None:
    """Negative age and a non-finite feels-like temperature are rejected."""
    with pytest.raises(ValueError):
        ThermalInput(
            air_temp=10.0,
            feels_like=10.0,
            wind_speed=1.0,
            rain_prob=10.0,
            uv_index=1.0,
            age=-1,
            personal_offset=0.0,
        )
    with pytest.raises(ValueError):
        calculate_effective_temperature(
            feels_like=math.nan,
            age=ADULT_AGE_YEARS,
            personal_offset=0.0,
        )


def test_domain_modules_do_not_import_web_or_database_frameworks() -> None:
    """Core and domain modules stay free of web and database libraries."""
    root = Path(__file__).resolve().parents[1] / "app"
    forbidden = {"fastapi", "starlette", "sqlalchemy", "asyncpg", "httpx", "pydantic"}
    for path in (root / "core" / "constants.py", root / "domain" / "thermal_engine.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(forbidden)

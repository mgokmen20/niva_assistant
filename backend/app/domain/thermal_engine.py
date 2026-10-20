"""Deterministic clothing decision engine.

The engine is pure domain code: it does not call weather APIs, databases,
or a web framework. Callers pass an already resolved feels-like temperature.

Standards consulted by this module:
    ASHRAE Standard 55 — Thermal Environmental Conditions for Human
    Occupancy. Comfort is a condition of mind; the personal offset is the
    bounded expression of that individual preference.
    UTCI — Universal Thermal Climate Index stress categories (Bröde et al.,
    2012). Outdoor heat and cold bands are classified from the effective
    temperature.
    ISO 9920 — estimation of clothing insulation by layered ensembles
    (base, mid, and outer). Accessories cover rain, sun, and extremity cold.
    Pediatric thermoregulation — children exchange heat faster than adults
    because of a higher surface-area-to-mass ratio (Falk, 1998). The child
    cold offset represents that rapid cooling.
    Geriatric thermoregulation — older adults have blunted thermal
    perception and weaker vasoconstriction (Kenney and Munce, 2003). The
    senior cold offset represents that reduced cold defense.
"""

import math
from dataclasses import dataclass
from typing import TypedDict

from ..core.constants import (
    AGE_CHILD_THRESHOLD,
    AGE_MIN_YEARS,
    AGE_SENIOR_THRESHOLD,
    CARDIGAN,
    CHILD_COLD_OFFSET_CELSIUS,
    CHILD_UV_PROTECTION_MIN_INDEX,
    CLOTHING_CHILLY_BELOW_C,
    CLOTHING_FREEZING_BELOW_C,
    CLOTHING_MILD_BELOW_C,
    CLOTHING_WARM_BELOW_C,
    COMFORT_MAX_C,
    COMFORT_MIN_C,
    EXTREME_COLD_C,
    EXTREME_HEAT_C,
    FEEDBACK_MAX_OFFSET,
    FEEDBACK_MIN_OFFSET,
    FLEECE_MID_LAYER,
    GLOVES,
    INSULATED_MID_LAYER,
    LIGHT_JACKET,
    LIGHT_T_SHIRT,
    LONG_SLEEVE_BASE,
    MODERATE_COLD_MAX_C,
    MODERATE_COLD_MIN_C,
    PROBABILITY_MAX_PERCENT,
    PROBABILITY_MIN_PERCENT,
    RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT,
    WMO_PRECIPITATION_CODE_MIN,
    SCARF,
    SENIOR_COLD_OFFSET_CELSIUS,
    SLIGHT_COLD_MAX_C,
    SLIGHT_COLD_MIN_C,
    SUN_HAT,
    SUNGLASSES,
    THERMAL_BASE_LAYER,
    UMBRELLA,
    UV_INDEX_MIN,
    UV_PROTECTION_MIN_INDEX,
    WARM_HAT,
    WATERPROOF_SHELL,
    WIND_SHELL,
    WIND_SHELL_MIN_MPS,
    WIND_SPEED_MIN_MPS,
    WINTER_COAT,
    ZIP_HOODIE,
    ClothingBand,
    ClothingItem,
    ThermalStressCategory,
)


class LayerRecommendation(TypedDict):
    """One recommended garment, without a removability flag."""

    id: str
    label: str
    category: str


class MidLayerRecommendation(TypedDict):
    """Mid-layer garment plus whether the wearer can shed it."""

    id: str
    label: str
    category: str
    removable: bool


class ClothingRecommendation(TypedDict):
    """Layered ensemble selected for one effective temperature."""

    base_layer: LayerRecommendation
    mid_layer: MidLayerRecommendation | None
    outer_layer: LayerRecommendation | None
    accessories: list[LayerRecommendation]


@dataclass(frozen=True, slots=True)
class _Ensemble:
    """Temperature-band wardrobe before rain, wind, and sun adjustments."""

    base: ClothingItem
    mid: ClothingItem | None
    mid_removable: bool
    accessories: tuple[ClothingItem, ...]


_ENSEMBLES: dict[ClothingBand, _Ensemble] = {
    ClothingBand.FREEZING: _Ensemble(
        base=THERMAL_BASE_LAYER,
        mid=INSULATED_MID_LAYER,
        mid_removable=False,
        accessories=(WARM_HAT, SCARF, GLOVES),
    ),
    ClothingBand.CHILLY: _Ensemble(
        base=LONG_SLEEVE_BASE,
        mid=FLEECE_MID_LAYER,
        mid_removable=False,
        accessories=(),
    ),
    ClothingBand.MILD: _Ensemble(
        base=LIGHT_T_SHIRT,
        mid=None,
        mid_removable=False,
        accessories=(),
    ),
    ClothingBand.WARM: _Ensemble(
        base=LIGHT_T_SHIRT,
        mid=None,
        mid_removable=False,
        accessories=(),
    ),
    ClothingBand.HOT: _Ensemble(
        base=LIGHT_T_SHIRT,
        mid=None,
        mid_removable=False,
        accessories=(SUNGLASSES,),
    ),
}


def _require_finite(name: str, value: float) -> float:
    """Return ``value`` as a float, or raise if it is not finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def _require_age(age: int) -> int:
    """Return ``age`` when it is a whole number of years at or above the minimum."""
    if isinstance(age, bool) or not isinstance(age, int) or age < AGE_MIN_YEARS:
        raise ValueError(f"age must be an integer greater than or equal to {AGE_MIN_YEARS}.")
    return age


def _require_at_least(name: str, value: float, minimum: float) -> float:
    """Return ``value`` when it is finite and greater than or equal to ``minimum``."""
    number = _require_finite(name, value)
    if number < minimum:
        raise ValueError(f"{name} must be greater than or equal to {minimum}.")
    return number


def _require_percent(name: str, value: float) -> float:
    """Return a percentage constrained to the closed 0–100 interval."""
    number = _require_finite(name, value)
    if number < PROBABILITY_MIN_PERCENT or number > PROBABILITY_MAX_PERCENT:
        raise ValueError(
            f"{name} must be between {PROBABILITY_MIN_PERCENT} and {PROBABILITY_MAX_PERCENT}."
        )
    return number


def _clamp_personal_offset(personal_offset: float) -> float:
    """Clamp a wearer offset to the ASHRAE-style feedback bounds."""
    offset = _require_finite("personal_offset", personal_offset)
    if offset < FEEDBACK_MIN_OFFSET:
        return FEEDBACK_MIN_OFFSET
    if offset > FEEDBACK_MAX_OFFSET:
        return FEEDBACK_MAX_OFFSET
    return offset


def _is_child(age: int) -> bool:
    """Return whether ``age`` is below the pediatric threshold."""
    return age < AGE_CHILD_THRESHOLD


def _age_cold_offset(age: int) -> float:
    """Return the age compensation subtracted from feels-like temperature.

    Seniors at or above ``AGE_SENIOR_THRESHOLD`` lose
    ``SENIOR_COLD_OFFSET_CELSIUS``. That shift stands in for blunted cold
    perception and reduced vasoconstriction in older adults (Kenney and
    Munce, 2003). Children under ``AGE_CHILD_THRESHOLD`` lose
    ``CHILD_COLD_OFFSET_CELSIUS`` because a higher surface-area-to-mass
    ratio cools them faster (Falk, 1998). Every other age contributes no
    age shift. The two groups do not overlap.
    """
    validated_age = _require_age(age)
    if validated_age >= AGE_SENIOR_THRESHOLD:
        return SENIOR_COLD_OFFSET_CELSIUS
    if validated_age < AGE_CHILD_THRESHOLD:
        return CHILD_COLD_OFFSET_CELSIUS
    return 0.0


def _uv_protection_min_index(age: int) -> float:
    """Return the ultraviolet index at which sun protection is selected."""
    if _is_child(age):
        return CHILD_UV_PROTECTION_MIN_INDEX
    return UV_PROTECTION_MIN_INDEX


def _layer(item: ClothingItem) -> LayerRecommendation:
    """Map a catalog item to the recommendation payload."""
    return {
        "id": item.id,
        "label": item.label,
        "category": item.category.value,
    }


def _mid_layer(item: ClothingItem | None, removable: bool) -> MidLayerRecommendation | None:
    """Map a mid-layer item, including whether it can be taken off."""
    if item is None:
        return None
    payload = _layer(item)
    return {
        "id": payload["id"],
        "label": payload["label"],
        "category": payload["category"],
        "removable": removable,
    }


def _append_unique(items: list[ClothingItem], item: ClothingItem) -> None:
    """Append ``item`` when that garment is not already in ``items``."""
    if item not in items:
        items.append(item)


def classify_clothing_band(effective_temp: float) -> ClothingBand:
    """Return the European layering band for an effective temperature.

    The cuts are ``CLOTHING_FREEZING_BELOW_C``, ``CLOTHING_CHILLY_BELOW_C``,
    ``CLOTHING_MILD_BELOW_C``, and ``CLOTHING_WARM_BELOW_C``. A value on a
    boundary belongs to the warmer band.
    """
    temperature = _require_finite("effective_temp", effective_temp)
    if temperature < CLOTHING_FREEZING_BELOW_C:
        return ClothingBand.FREEZING
    if temperature < CLOTHING_CHILLY_BELOW_C:
        return ClothingBand.CHILLY
    if temperature < CLOTHING_MILD_BELOW_C:
        return ClothingBand.MILD
    if temperature < CLOTHING_WARM_BELOW_C:
        return ClothingBand.WARM
    return ClothingBand.HOT


def precipitation_active(rain_probability_percent: float, weather_code: int = 0) -> bool:
    """True when the chance of precipitation or the WMO code calls for rain gear.

    The probability cut is ``RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT``.
    A code of ``WMO_PRECIPITATION_CODE_MIN`` or higher is drizzle, rain,
    showers, snow, or thunder.
    """
    if rain_probability_percent >= RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT:
        return True
    return weather_code >= WMO_PRECIPITATION_CODE_MIN


def _select_outer(
    band: ClothingBand,
    wind_speed: float,
    rain_prob: float,
    weather_code: int,
) -> ClothingItem | None:
    """Choose the outer garment for the clothing band, wind, and rain.

    Freezing keeps the winter coat. Chilly and mild always keep a jacket,
    trench, or shell, so those slots are never empty. Warm adds a shell
    only for rain or wind. Hot leaves the outer slot empty: a coat would
    trap heat, and wind in that band assists cooling.
    """
    raining = precipitation_active(rain_prob, weather_code)
    windy = wind_speed >= WIND_SHELL_MIN_MPS
    if band is ClothingBand.FREEZING:
        return WINTER_COAT
    if band is ClothingBand.CHILLY:
        if raining:
            return WATERPROOF_SHELL
        if windy:
            return WIND_SHELL
        return LIGHT_JACKET
    if band is ClothingBand.MILD:
        if raining:
            return WATERPROOF_SHELL
        return LIGHT_JACKET
    if band is ClothingBand.WARM and raining:
        return WATERPROOF_SHELL
    if band is ClothingBand.WARM and windy:
        return WIND_SHELL
    if band is ClothingBand.HOT and raining:
        return WATERPROOF_SHELL
    return None


def _child_mid_item(band: ClothingBand) -> ClothingItem | None:
    """Return the removable child mid-layer for a cold clothing band.

    Zip hoodies cover freezing and chilly weather: they still add
    insulation, and the zipper lets a child shed heat quickly. Mild
    weather uses a cardigan. Warm and hot bands do not add a mid layer.
    """
    if band in {ClothingBand.FREEZING, ClothingBand.CHILLY}:
        return ZIP_HOODIE
    if band is ClothingBand.MILD:
        return CARDIGAN
    return None


def _resolve_mid_layer(
    band: ClothingBand,
    ensemble: _Ensemble,
    age: int,
) -> MidLayerRecommendation | None:
    """Choose the mid layer, forcing a removable child garment when required."""
    if _is_child(age):
        child_mid = _child_mid_item(band)
        if child_mid is not None:
            return _mid_layer(child_mid, True)
    return _mid_layer(ensemble.mid, ensemble.mid_removable)


def _select_accessories(
    band: ClothingBand,
    ensemble: _Ensemble,
    wind_speed: float,
    rain_prob: float,
    uv_index: float,
    uv_threshold: float,
    weather_code: int,
) -> list[LayerRecommendation]:
    """Add rain, sun, and wind accessories on top of the band defaults."""
    items: list[ClothingItem] = list(ensemble.accessories)
    if band is ClothingBand.CHILLY and wind_speed >= WIND_SHELL_MIN_MPS:
        _append_unique(items, GLOVES)
    if precipitation_active(rain_prob, weather_code):
        _append_unique(items, UMBRELLA)
    if uv_index >= uv_threshold:
        _append_unique(items, SUNGLASSES)
    if band is ClothingBand.HOT and uv_index >= uv_threshold:
        _append_unique(items, SUN_HAT)
    return [_layer(item) for item in items]


@dataclass(frozen=True, slots=True)
class ThermalInput:
    """Observed conditions and wearer traits for one recommendation.

    ``air_temp`` is the dry-bulb air temperature in degrees Celsius, kept
    so callers can show it beside the decision. Classification uses
    ``feels_like`` (UTCI or an equivalent apparent temperature), because
    that index already folds in wind and radiation. ``wind_speed`` is
    metres per second, ``rain_prob`` is a percentage from 0 to 100, and
    ``uv_index`` is the WHO ultraviolet index.

    Attributes:
        air_temp: Dry-bulb air temperature in degrees Celsius.
        feels_like: Apparent outdoor temperature in degrees Celsius.
        wind_speed: Wind speed in metres per second.
        rain_prob: Probability of rain as a percentage.
        uv_index: Ultraviolet index.
        age: Wearer age in whole years.
        personal_offset: Preferred comfort shift in degrees Celsius.
        weather_code: WMO code. Zero when the provider did not send one.
    """

    air_temp: float
    feels_like: float
    wind_speed: float
    rain_prob: float
    uv_index: float
    age: int
    personal_offset: float
    weather_code: int = 0

    def __post_init__(self) -> None:
        """Reject values that cannot describe a real outdoor exposure."""
        _require_finite("air_temp", self.air_temp)
        _require_finite("feels_like", self.feels_like)
        _require_at_least("wind_speed", self.wind_speed, WIND_SPEED_MIN_MPS)
        _require_percent("rain_prob", self.rain_prob)
        _require_at_least("uv_index", self.uv_index, UV_INDEX_MIN)
        _require_age(self.age)
        _require_finite("personal_offset", self.personal_offset)
        if isinstance(self.weather_code, bool) or not isinstance(self.weather_code, int) or self.weather_code < 0:
            raise ValueError("weather_code must be a non-negative WMO code.")

    def effective_temperature(self) -> float:
        """Return the clothing decision temperature for this observation."""
        return calculate_effective_temperature(
            feels_like=self.feels_like,
            age=self.age,
            personal_offset=self.personal_offset,
        )


def calculate_effective_temperature(
    feels_like: float,
    age: int,
    personal_offset: float,
) -> float:
    """Compute the temperature used to select clothing.

    The decision temperature is::

        T_effective = T_feels_like + delta_personal - delta_age

    ``delta_age`` is selected from the wearer age:

    - ``SENIOR_COLD_OFFSET_CELSIUS`` when age >= ``AGE_SENIOR_THRESHOLD``
    - ``CHILD_COLD_OFFSET_CELSIUS`` when age < ``AGE_CHILD_THRESHOLD``
    - 0.0 otherwise

    ``feels_like`` is the outdoor apparent temperature (UTCI or an
    equivalent feels-like index) in degrees Celsius. ``delta_personal``
    is the wearer comfort offset after clamping to
    [``FEEDBACK_MIN_OFFSET``, ``FEEDBACK_MAX_OFFSET``], the closed
    interval required for feedback. ``FEEDBACK_STEP_CELSIUS`` is the
    increment a wearer uses when adjusting that offset; this function
    does not round to the step, so a stored value of 0.25 stays 0.25.

    Subtracting ``delta_age`` treats the same environment as colder and
    selects a warmer ISO 9920 ensemble. For older adults the shift
    represents blunted cold perception and weaker vasoconstriction
    (Kenney and Munce, 2003). For children it represents faster heat loss
    from a higher surface-area-to-mass ratio (Falk, 1998). ASHRAE 55
    supplies the individual-preference term. UTCI supplies the outdoor
    scale the result is classified on.

    Args:
        feels_like: Apparent outdoor temperature in degrees Celsius.
        age: Age in whole years.
        personal_offset: Preferred comfort shift in degrees Celsius.

    Returns:
        Effective temperature in degrees Celsius.
    """
    apparent_temperature = _require_finite("feels_like", feels_like)
    delta_personal = _clamp_personal_offset(personal_offset)
    delta_age = _age_cold_offset(age)
    return apparent_temperature + delta_personal - delta_age


def classify_utci_stress(effective_temp: float) -> ThermalStressCategory:
    """Classify an effective temperature on the UTCI stress scale.

    Intervals, in degrees Celsius:

    - extreme heat: temperature > 32.0
    - moderate heat: 26.0 < temperature <= 32.0
    - comfort (no thermal stress): 9.0 <= temperature <= 26.0
    - slight cold: 0.0 <= temperature < 9.0
    - moderate cold: -13.0 <= temperature < 0.0
    - extreme cold: temperature < -13.0

    Where two named ranges share an edge, the warmer category wins. That
    keeps 9.0 inside comfort, 0.0 inside slight cold, and -13.0 inside
    moderate cold, while honouring the strict UTCI cuts for extreme heat
    and extreme cold.

    Args:
        effective_temp: Decision temperature from
            :func:`calculate_effective_temperature`, in degrees Celsius.

    Returns:
        The matching UTCI stress category.
    """
    temperature = _require_finite("effective_temp", effective_temp)
    if temperature > EXTREME_HEAT_C:
        return ThermalStressCategory.EXTREME_HEAT
    if COMFORT_MAX_C < temperature <= EXTREME_HEAT_C:
        return ThermalStressCategory.MODERATE_HEAT
    if COMFORT_MIN_C <= temperature <= COMFORT_MAX_C:
        return ThermalStressCategory.COMFORT
    if SLIGHT_COLD_MIN_C <= temperature < SLIGHT_COLD_MAX_C:
        return ThermalStressCategory.SLIGHT_COLD
    if MODERATE_COLD_MIN_C <= temperature < MODERATE_COLD_MAX_C:
        return ThermalStressCategory.MODERATE_COLD
    if temperature < EXTREME_COLD_C:
        return ThermalStressCategory.EXTREME_COLD
    raise ValueError(f"effective_temp {temperature} does not match a UTCI band.")


def determine_clothing_layers(
    effective_temp: float,
    wind_speed: float,
    rain_prob: float,
    uv_index: float,
    age: int,
    weather_code: int = 0,
) -> ClothingRecommendation:
    """Select a layered outfit for an effective temperature, weather, and age.

    The base, mid, and outer slots follow ISO 9920 layering. The European
    clothing band of ``effective_temp`` chooses the insulating ensemble.
    Callers should pass the result of :func:`calculate_effective_temperature`,
    so wind already present in the feels-like temperature, the personal
    offset, and the age offset are applied before any garment is chosen.
    This function uses ``age`` only for garment style and sun protection.
    Wind at or above ``WIND_SHELL_MIN_MPS`` still selects a windbreaker in
    the chilly and warm bands, and gloves in the chilly band.

    Freezing weather keeps a required adult mid layer. Chilly weather
    always includes both a mid layer and an outer layer. Mild weather
    keeps a light jacket or, for a child, a removable cardigan. Children
    under ``AGE_CHILD_THRESHOLD`` receive a removable zip hoodie in
    freezing and chilly weather. Pediatric heat exchange is fast in both
    directions, so a layer that can be opened matters as much as the extra
    insulation (Falk, 1998).

    Accessories:

    - warm hat, scarf, and gloves below 5 °C
    - gloves in the chilly band when wind reaches ``WIND_SHELL_MIN_MPS``
    - umbrella when rain probability is at least 15 percent or the WMO code is 51 or higher
    - sunglasses at 24 °C and above, and whenever ``uv_index`` reaches 3.0
      (2.5 for a child)
    - sun hat in the hot band when that UV trigger fires

    Args:
        effective_temp: Decision temperature in degrees Celsius.
        wind_speed: Wind speed in metres per second.
        rain_prob: Probability of rain as a percentage from 0 to 100.
        uv_index: WHO ultraviolet index.
        age: Wearer age in whole years.

    Returns:
        Base layer, optional mid layer (with ``removable`` when present),
        optional outer layer, and accessories.
    """
    validated_wind = _require_at_least("wind_speed", wind_speed, WIND_SPEED_MIN_MPS)
    validated_rain = _require_percent("rain_prob", rain_prob)
    validated_uv = _require_at_least("uv_index", uv_index, UV_INDEX_MIN)
    validated_age = _require_age(age)
    if isinstance(weather_code, bool) or not isinstance(weather_code, int) or weather_code < 0:
        raise ValueError("weather_code must be a non-negative WMO code.")
    band = classify_clothing_band(effective_temp)
    ensemble = _ENSEMBLES[band]
    outer = _select_outer(band, validated_wind, validated_rain, weather_code)
    return {
        "base_layer": _layer(ensemble.base),
        "mid_layer": _resolve_mid_layer(band, ensemble, validated_age),
        "outer_layer": _layer(outer) if outer is not None else None,
        "accessories": _select_accessories(
            band,
            ensemble,
            validated_wind,
            validated_rain,
            validated_uv,
            _uv_protection_min_index(validated_age),
            weather_code,
        ),
    }

"""Adjust a finished outfit for walking, everyday wear, or sitting still.

The calibrated recommendation stays the balanced outfit. Light raises the
decision temperature by ``OUTFIT_PREFERENCE_SHIFT_CELSIUS`` and sheds a
mid or outer layer. Warm lowers it by the same amount, steps the outer
layer up, and adds a warm hat and gloves when they are missing.
"""

from typing import Any, Final

from ..core.constants import (
    GLOVES,
    LIGHT_JACKET,
    OUTFIT_PREFERENCE_AUTO,
    OUTFIT_PREFERENCE_BALANCED,
    OUTFIT_PREFERENCE_LIGHT,
    OUTFIT_PREFERENCE_SHIFT_CELSIUS,
    OUTFIT_PREFERENCE_WARM,
    RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT,
    SCARF,
    WARM_HAT,
    WATERPROOF_SHELL,
    WINTER_COAT,
    ClothingItem,
)

_ALLOWED: Final[frozenset[str]] = frozenset(
    {
        OUTFIT_PREFERENCE_AUTO,
        OUTFIT_PREFERENCE_BALANCED,
        OUTFIT_PREFERENCE_LIGHT,
        OUTFIT_PREFERENCE_WARM,
    }
)
_COLD_ACCESSORY_IDS: Final[frozenset[str]] = frozenset({WARM_HAT.id, GLOVES.id, SCARF.id})
_LIGHT_OUTER_IDS: Final[frozenset[str]] = frozenset({"light_jacket", "wind_shell"})


def normalize_outfit_preference(mode: str) -> str:
    """Map a request mode onto light, balanced, or warm.

    ``auto`` is the historical client default and means balanced.
    """
    text = mode.strip().lower()
    if text not in _ALLOWED:
        allowed = ", ".join(sorted(_ALLOWED))
        raise ValueError(f"Outfit preference must be one of: {allowed}.")
    if text == OUTFIT_PREFERENCE_AUTO:
        return OUTFIT_PREFERENCE_BALANCED
    return text


def preference_temperature_shift(preference: str) -> float:
    """Return the decision-temperature shift for one preference."""
    normalized = normalize_outfit_preference(preference)
    if normalized == OUTFIT_PREFERENCE_LIGHT:
        return OUTFIT_PREFERENCE_SHIFT_CELSIUS
    if normalized == OUTFIT_PREFERENCE_WARM:
        return -OUTFIT_PREFERENCE_SHIFT_CELSIUS
    return 0.0


def apply_outfit_preference(
    recommendation: dict[str, Any],
    preference: str,
    *,
    rain_probability_percent: float,
) -> str:
    """Shift the decision temperature and the layers for one preference.

    Balanced leaves the engine outfit unchanged. The returned value is the
    normalized preference, so callers can speak it in the voice summary.
    """
    normalized = normalize_outfit_preference(preference)
    current = float(recommendation["effective_temperature_celsius"])
    recommendation["effective_temperature_celsius"] = current + preference_temperature_shift(normalized)
    if normalized == OUTFIT_PREFERENCE_WARM:
        _apply_warm(recommendation)
    elif normalized == OUTFIT_PREFERENCE_LIGHT:
        _apply_light(recommendation, rain_probability_percent)
    return normalized


def _garment_payload(item: ClothingItem) -> dict[str, str]:
    """Map a catalog item onto the recommendation garment shape."""
    return {"id": item.id, "label": item.label, "category": item.category.value}


def _layer_id(layer: object) -> str | None:
    """Return a garment id when ``layer`` is a garment dictionary."""
    if not isinstance(layer, dict):
        return None
    garment_id = layer.get("id")
    if not isinstance(garment_id, str) or garment_id == "":
        return None
    return garment_id


def _set_outer(recommendation: dict[str, Any], item: ClothingItem | None) -> None:
    """Replace the outer layer, or clear it when the preference sheds it."""
    recommendation["outer_layer"] = None if item is None else _garment_payload(item)


def _accessories(recommendation: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the accessory list, creating it when the provider omitted it."""
    raw = recommendation.get("accessories")
    if not isinstance(raw, list):
        recommendation["accessories"] = []
        return recommendation["accessories"]
    return raw


def _add_accessory(recommendation: dict[str, Any], item: ClothingItem) -> None:
    """Append an accessory when that id is not already recommended."""
    accessories = _accessories(recommendation)
    if any(_layer_id(row) == item.id for row in accessories):
        return
    accessories.append(_garment_payload(item))


def _apply_warm(recommendation: dict[str, Any]) -> None:
    """Step the outer layer up and keep hands and head covered."""
    outer_id = _layer_id(recommendation.get("outer_layer"))
    if outer_id in {None, "wind_shell"}:
        _set_outer(recommendation, LIGHT_JACKET)
    elif outer_id == LIGHT_JACKET.id:
        _set_outer(recommendation, WINTER_COAT)
    _add_accessory(recommendation, WARM_HAT)
    _add_accessory(recommendation, GLOVES)


def _apply_light(recommendation: dict[str, Any], rain_probability_percent: float) -> None:
    """Drop the mid layer and lighten the outer layer.

    Rain at or above the umbrella threshold keeps a waterproof shell so a
    lighter outfit does not lose rain protection.
    """
    recommendation["mid_layer"] = None
    outer_id = _layer_id(recommendation.get("outer_layer"))
    raining = (
        rain_probability_percent >= RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT
        or outer_id == WATERPROOF_SHELL.id
    )
    if outer_id == WINTER_COAT.id:
        _set_outer(recommendation, WATERPROOF_SHELL if raining else LIGHT_JACKET)
    elif outer_id in _LIGHT_OUTER_IDS or outer_id == WATERPROOF_SHELL.id:
        _set_outer(recommendation, WATERPROOF_SHELL if raining else None)
    accessories = _accessories(recommendation)
    recommendation["accessories"] = [
        row for row in accessories if _layer_id(row) not in _COLD_ACCESSORY_IDS
    ]

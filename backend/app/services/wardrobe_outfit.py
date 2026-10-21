"""Build a wearable pool from owned clothes and generic fallbacks.

The thermal engine still decides the effective temperature. This module
only decides which names are eligible for the stylist.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..core.constants import (
    CLOTHING_CHILLY_BELOW_C,
    CLOTHING_MILD_BELOW_C,
    DAILY_VARIANCE_HIGH_ABOVE_C,
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
    WARDROBE_LIGHT_GARMENT_BELOW_C,
    WARDROBE_RAIN_EXTRA_ABOVE_PERCENT,
    WARDROBE_SUN_EXTRA_MIN_UV,
    WIND_SHELL_MIN_MPS,
    ClothingBand,
    ClothingCategory,
)
from ..domain.thermal_engine import classify_clothing_band, precipitation_active

ROLE_TOP = "top"
ROLE_BOTTOM = "bottom"
ROLE_OUTERWEAR = "outerwear"
ROLE_EXTRA = "extra"
SLOT_TOP = "TOP"
SLOT_BOTTOM = "BOTTOM"
SLOT_OUTERWEAR = "OUTERWEAR"
PLAN_SINGLE = "single"
PLAN_REMOVABLE = "removable"
PLAN_COLD_PAIR = "cold_pair"

_TOP_CATEGORIES = frozenset({"T-Shirt", "Sweater"})
_BOTTOM_CATEGORIES = frozenset({"Pants", "Shorts"})


class OwnedGarment(Protocol):
    """Fields the pool needs from one wardrobe row."""

    category: str
    thickness: str
    color_name: str
    style: str
    is_waterproof: bool
    item_name: str


@dataclass(frozen=True, slots=True)
class PoolItem:
    """One name the stylist may accept or reject."""

    name: str
    role: str
    item_id: str
    category: str
    detail: str = ""
    wardrobe_category: str = ""
    thickness: str = ""
    image_url: str | None = None
    waterproof: bool = False


@dataclass(frozen=True, slots=True)
class HybridPool:
    """Eligible clothes plus whether an outer layer is required."""

    items: tuple[PoolItem, ...]
    outerwear_required: bool
    layer_plan: str = PLAN_SINGLE


def outerwear_required(
    effective_temperature_celsius: float,
    *,
    wind_speed_mps: float,
    rain_probability_percent: float,
    weather_code: int,
) -> bool:
    """Return whether the clothing band needs an outer layer.

    Freezing, chilly, and mild weather always do. Warm weather does when
    it is raining or windy. Hot weather does only when rain gear is due.
    Those are the same cuts as the thermal engine's outer-layer choice.
    """
    band = classify_clothing_band(effective_temperature_celsius)
    raining = precipitation_active(rain_probability_percent, weather_code)
    if band in {ClothingBand.FREEZING, ClothingBand.CHILLY, ClothingBand.MILD}:
        return True
    if raining:
        return True
    return band is ClothingBand.WARM and wind_speed_mps >= WIND_SHELL_MIN_MPS


def layer_plan(
    min_temperature_celsius: float | None,
    max_temperature_celsius: float | None,
) -> str:
    """Choose how many upper-body layers the rest of the day needs.

    A swing above ``DAILY_VARIANCE_HIGH_ABOVE_C`` that starts chilly and
    reaches the warm band gets a T-shirt, a removable sweater, and one coat.
    A day that stays cold gets the sweater and one coat, and nothing else
    on the upper body.
    """
    if min_temperature_celsius is None or max_temperature_celsius is None:
        return PLAN_SINGLE
    if max_temperature_celsius < min_temperature_celsius:
        return PLAN_SINGLE
    variance = max_temperature_celsius - min_temperature_celsius
    crosses = (
        min_temperature_celsius < CLOTHING_CHILLY_BELOW_C
        and max_temperature_celsius >= CLOTHING_MILD_BELOW_C
    )
    if variance > DAILY_VARIANCE_HIGH_ABOVE_C and crosses:
        return PLAN_REMOVABLE
    if max_temperature_celsius < CLOTHING_CHILLY_BELOW_C:
        return PLAN_COLD_PAIR
    return PLAN_SINGLE


def build_hybrid_pool(
    garments: list[OwnedGarment],
    *,
    effective_temperature_celsius: float,
    wind_speed_mps: float,
    rain_probability_percent: float,
    uv_index: float,
    weather_code: int,
    min_temperature_celsius: float | None = None,
    max_temperature_celsius: float | None = None,
) -> HybridPool:
    """Filter owned clothes and fill any missing core slot.

    Shorts and thin items are removed below ``WARDROBE_LIGHT_GARMENT_BELOW_C``.
    A missing top, bottom, or required outer layer is filled with a generic
    name. Rain above 40 percent adds an umbrella. The waterproof coat, when
    needed, is the single outerwear item. High UV or hot weather adds sun extras.
    """
    band = classify_clothing_band(effective_temperature_celsius)
    plan = layer_plan(min_temperature_celsius, max_temperature_celsius)
    needs_outer = outerwear_required(
        effective_temperature_celsius,
        wind_speed_mps=wind_speed_mps,
        rain_probability_percent=rain_probability_percent,
        weather_code=weather_code,
    ) or plan in {PLAN_REMOVABLE, PLAN_COLD_PAIR}
    rain_high = rain_probability_percent > WARDROBE_RAIN_EXTRA_ABOVE_PERCENT
    used_names: set[str] = set()
    items: list[PoolItem] = []
    for garment in garments:
        if not _temperature_allows(garment, effective_temperature_celsius):
            continue
        role = _role_for_category(garment.category)
        if role is None:
            continue
        name = _unique_name(garment.item_name, used_names)
        items.append(
            PoolItem(
                name=name,
                role=role,
                item_id=_slug(name),
                category=_slot_category(garment.category),
                detail=_garment_detail(garment),
                wardrobe_category=garment.category,
                thickness=garment.thickness,
                image_url=_image_url(garment),
                waterproof=bool(garment.is_waterproof),
            )
        )
    _ensure_plan_items(
        items,
        plan=plan,
        band=band,
        effective_temperature_celsius=effective_temperature_celsius,
        needs_outer=needs_outer,
        rain_high=rain_high,
        used_names=used_names,
    )
    items.extend(
        _condition_extras(
            band,
            rain_probability_percent=rain_probability_percent,
            uv_index=uv_index,
            used_names=used_names,
        )
    )
    return HybridPool(items=tuple(items), outerwear_required=needs_outer, layer_plan=plan)


def choose_fallback_outfit(
    pool: HybridPool,
    rng: random.Random | None = None,
) -> list[PoolItem]:
    """Pick one top, one bottom, and one outer layer when the model fails.

    Condition extras stay in the result. They were added because of rain
    or sun, so dropping them would hide a weather precaution.
    """
    chooser = rng if rng is not None else random
    chosen: list[PoolItem] = []
    for role, required in (
        (ROLE_TOP, True),
        (ROLE_BOTTOM, True),
        (ROLE_OUTERWEAR, pool.outerwear_required),
    ):
        if not required:
            continue
        options = [item for item in pool.items if item.role == role]
        if options:
            chosen.append(chooser.choice(options))
    chosen.extend(item for item in pool.items if item.role == ROLE_EXTRA)
    return chosen


def complete_selection(
    pool: HybridPool,
    accepted_names: list[str],
    rng: random.Random | None = None,
) -> list[PoolItem]:
    """Keep one accepted item per core role and fill anything still missing.

    Extras stay only when the model marked them true. A second top, bottom,
    or coat is ignored. An outer layer is ignored when the temperature
    does not need one.
    """
    chooser = rng if rng is not None else random
    by_name = {item.name: item for item in pool.items}
    chosen: list[PoolItem] = []
    seen: set[str] = set()
    filled_roles: set[str] = set()
    for name in accepted_names:
        item = by_name.get(name)
        if item is None or item.name in seen:
            continue
        if item.role in {ROLE_TOP, ROLE_BOTTOM, ROLE_OUTERWEAR}:
            if item.role in filled_roles:
                continue
            if item.role == ROLE_OUTERWEAR and not pool.outerwear_required:
                continue
            filled_roles.add(item.role)
        chosen.append(item)
        seen.add(item.name)
    for role, required in (
        (ROLE_TOP, True),
        (ROLE_BOTTOM, True),
        (ROLE_OUTERWEAR, pool.outerwear_required),
    ):
        if not required or role in filled_roles:
            continue
        options = [item for item in pool.items if item.role == role and item.name not in seen]
        if not options:
            continue
        pick = chooser.choice(options)
        chosen.append(pick)
        seen.add(pick.name)
    return chosen


def assign_outfit(
    pool: HybridPool,
    accepted_names: list[str] | None,
    rng: random.Random | None = None,
) -> list[PoolItem]:
    """Keep one bottom, at most one coat, and the tops the day plan allows.

    ``accepted_names`` is None when the model reply could not be parsed.
    The required roles are then chosen from the pool. Extras stay when the
    model marked them true, and also when the model reply was unusable.
    """
    chooser = rng if rng is not None else random.Random()
    accepted = set(accepted_names or [])
    chosen: list[PoolItem] = []
    if pool.layer_plan == PLAN_REMOVABLE:
        shirt = _prefer(pool, chooser, accepted, _is_shirt)
        sweater = _prefer(pool, chooser, accepted, _is_sweater)
        if shirt is not None:
            chosen.append(shirt)
        if sweater is not None and (shirt is None or sweater.name != shirt.name):
            chosen.append(sweater)
    elif pool.layer_plan == PLAN_COLD_PAIR:
        sweater = _prefer(pool, chooser, accepted, _is_sweater, prefer_thick=True)
        if sweater is None:
            sweater = _prefer(pool, chooser, accepted, lambda item: item.role == ROLE_TOP)
        if sweater is not None:
            chosen.append(sweater)
    else:
        top = _prefer(pool, chooser, accepted, lambda item: item.role == ROLE_TOP)
        if top is not None:
            chosen.append(top)
    bottom = _prefer(pool, chooser, accepted, lambda item: item.role == ROLE_BOTTOM)
    if bottom is not None:
        chosen.append(bottom)
    if pool.outerwear_required:
        outer = _prefer(pool, chooser, accepted, lambda item: item.role == ROLE_OUTERWEAR, prefer_waterproof=True)
        if outer is not None:
            chosen.append(outer)
    if accepted_names is None:
        chosen.extend(item for item in pool.items if item.role == ROLE_EXTRA)
    else:
        chosen.extend(item for item in pool.items if item.role == ROLE_EXTRA and item.name in accepted)
    return chosen


def layers_from_selection(selected: list[PoolItem], layer_plan_name: str = PLAN_SINGLE) -> dict[str, object]:
    """Map a selection onto top, bottom, outerwear, and accessory slots.

    Legacy base, mid, and outer keys stay so older readers still see the
    upper-body pieces. The bottom is never stored as a base layer.
    """
    tops = [item for item in selected if item.role == ROLE_TOP]
    if not tops:
        raise ValueError("An outfit needs at least one top.")
    bottom = next((item for item in selected if item.role == ROLE_BOTTOM), None)
    outer = next((item for item in selected if item.role == ROLE_OUTERWEAR), None)
    extras = [item for item in selected if item.role == ROLE_EXTRA]
    top_payloads = [
        _payload(item, removable=layer_plan_name == PLAN_REMOVABLE and _is_sweater(item))
        for item in tops
    ]
    outer_payload = None if outer is None else _payload(outer)
    return {
        "tops": top_payloads,
        "bottom": None if bottom is None else _payload(bottom),
        "outerwear": outer_payload,
        "accessories": [_payload(item) for item in extras],
        "base_layer": top_payloads[0],
        "mid_layer": top_payloads[1] if len(top_payloads) > 1 else None,
        "outer_layer": outer_payload,
        "wardrobe_selection": [item.name for item in selected],
        "layer_plan": layer_plan_name,
    }


def _garment_detail(garment: OwnedGarment) -> str:
    """Describe color, style, and thickness for the stylist prompt."""
    detail = f"color {garment.color_name}, style {garment.style}, thickness {garment.thickness}"
    if garment.is_waterproof:
        return f"{detail}, waterproof"
    return detail


def _temperature_allows(garment: OwnedGarment, effective_temperature_celsius: float) -> bool:
    """Drop shorts and thin cloth when the decision temperature is cold."""
    if effective_temperature_celsius >= WARDROBE_LIGHT_GARMENT_BELOW_C:
        return True
    if garment.category == "Shorts" or garment.thickness == "Thin":
        return False
    return True


def _role_for_category(category: str) -> str | None:
    """Map a wardrobe category onto a stylist role."""
    if category in _TOP_CATEGORIES:
        return ROLE_TOP
    if category in _BOTTOM_CATEGORIES:
        return ROLE_BOTTOM
    if category == "Outerwear":
        return ROLE_OUTERWEAR
    if category == "Accessory":
        return ROLE_EXTRA
    return None


def _slot_category(wardrobe_category: str) -> str:
    """Map a wardrobe category onto a top, bottom, outerwear, or accessory slot."""
    if wardrobe_category in _TOP_CATEGORIES:
        return SLOT_TOP
    if wardrobe_category in _BOTTOM_CATEGORIES:
        return SLOT_BOTTOM
    if wardrobe_category == "Outerwear":
        return SLOT_OUTERWEAR
    return ClothingCategory.ACCESSORY.value


def _fallback_top(band: ClothingBand, used_names: set[str]) -> PoolItem:
    """Supply a warm sweater in the cold bands and a T-shirt otherwise."""
    if band in {ClothingBand.FREEZING, ClothingBand.CHILLY}:
        return _named_top(STANDARD_WARM_SWEATER_NAME, "standard_warm_sweater", "Sweater", "Thick", used_names)
    return _named_top(STANDARD_TSHIRT_NAME, "standard_t_shirt", "T-Shirt", "Normal", used_names)


def _fallback_bottom(
    band: ClothingBand,
    effective_temperature_celsius: float,
    used_names: set[str],
) -> PoolItem:
    """Supply shorts only on a hot day. Every colder day gets pants."""
    if band is ClothingBand.HOT and effective_temperature_celsius >= WARDROBE_LIGHT_GARMENT_BELOW_C:
        name = STANDARD_CASUAL_SHORTS_NAME
        item_id = "standard_casual_shorts"
    else:
        name = STANDARD_CASUAL_PANTS_NAME
        item_id = "standard_casual_pants"
    return PoolItem(
        name=_unique_name(name, used_names),
        role=ROLE_BOTTOM,
        item_id=item_id,
        category=SLOT_BOTTOM,
        wardrobe_category="Shorts" if item_id == "standard_casual_shorts" else "Pants",
    )


def _fallback_outer(band: ClothingBand, used_names: set[str], *, rain_high: bool) -> PoolItem:
    """Supply one coat. Heavy rain uses the raincoat instead of a second shell."""
    if rain_high:
        name = EXTRA_RAINCOAT_NAME
        item_id = "waterproof_shell"
        waterproof = True
    elif band is ClothingBand.FREEZING:
        name = STANDARD_WINTER_COAT_NAME
        item_id = "standard_winter_coat"
        waterproof = False
    else:
        name = STANDARD_LIGHT_JACKET_NAME
        item_id = "standard_light_jacket"
        waterproof = False
    return PoolItem(
        name=_unique_name(name, used_names),
        role=ROLE_OUTERWEAR,
        item_id=item_id,
        category=SLOT_OUTERWEAR,
        wardrobe_category="Outerwear",
        waterproof=waterproof,
    )


def _condition_extras(
    band: ClothingBand,
    *,
    rain_probability_percent: float,
    uv_index: float,
    used_names: set[str],
) -> list[PoolItem]:
    """Add rain or sun items when the conditions call for them."""
    extras: list[tuple[str, str]] = []
    if rain_probability_percent > WARDROBE_RAIN_EXTRA_ABOVE_PERCENT:
        extras.append((EXTRA_UMBRELLA_NAME, "umbrella"))
    if uv_index >= WARDROBE_SUN_EXTRA_MIN_UV or band is ClothingBand.HOT:
        extras.append((EXTRA_SUNGLASSES_NAME, "sunglasses"))
        extras.append((EXTRA_SUNSCREEN_NAME, "sunscreen"))
    added: list[PoolItem] = []
    for name, item_id in extras:
        if name in used_names:
            continue
        added.append(
            PoolItem(
                name=_unique_name(name, used_names),
                role=ROLE_EXTRA,
                item_id=item_id,
                category=ClothingCategory.ACCESSORY.value,
            )
        )
    return added


def _unique_name(name: str, used_names: set[str]) -> str:
    """Keep JSON keys unique when two garments share a name."""
    cleaned = " ".join(name.split())
    candidate = cleaned if cleaned != "" else "Garment"
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate
    index = 2
    while f"{candidate} ({index})" in used_names:
        index += 1
    labeled = f"{candidate} ({index})"
    used_names.add(labeled)
    return labeled


def _slug(name: str) -> str:
    """Build a stable garment id from a wardrobe name."""
    chars = [character.lower() if character.isalnum() else "_" for character in name.strip()]
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"wardrobe_{slug}" if slug != "" else "wardrobe_item"


def _ensure_plan_items(
    items: list[PoolItem],
    *,
    plan: str,
    band: ClothingBand,
    effective_temperature_celsius: float,
    needs_outer: bool,
    rain_high: bool,
    used_names: set[str],
) -> None:
    """Fill only the slots the day plan still lacks."""
    if plan == PLAN_REMOVABLE:
        if not any(_is_shirt(item) for item in items):
            items.append(_named_top(STANDARD_TSHIRT_NAME, "standard_t_shirt", "T-Shirt", "Normal", used_names))
        if not any(_is_sweater(item) for item in items):
            items.append(_named_top(STANDARD_WARM_SWEATER_NAME, "standard_warm_sweater", "Sweater", "Thick", used_names))
    elif plan == PLAN_COLD_PAIR:
        if not any(_is_sweater(item) for item in items):
            items.append(_named_top(STANDARD_WARM_SWEATER_NAME, "standard_warm_sweater", "Sweater", "Thick", used_names))
    elif not any(item.role == ROLE_TOP for item in items):
        items.append(_fallback_top(band, used_names))
    if not any(item.role == ROLE_BOTTOM for item in items):
        items.append(_fallback_bottom(band, effective_temperature_celsius, used_names))
    if needs_outer and not any(item.role == ROLE_OUTERWEAR for item in items):
        items.append(_fallback_outer(band, used_names, rain_high=rain_high))


def _named_top(
    name: str,
    item_id: str,
    wardrobe_category: str,
    thickness: str,
    used_names: set[str],
) -> PoolItem:
    """Build one generic top with a stable id."""
    return PoolItem(
        name=_unique_name(name, used_names),
        role=ROLE_TOP,
        item_id=item_id,
        category=SLOT_TOP,
        wardrobe_category=wardrobe_category,
        thickness=thickness,
    )


def _is_shirt(item: PoolItem) -> bool:
    """True for a T-shirt top, including the generic fallback."""
    return item.role == ROLE_TOP and item.wardrobe_category == "T-Shirt"


def _is_sweater(item: PoolItem) -> bool:
    """True for a sweater top, including the generic fallback."""
    return item.role == ROLE_TOP and item.wardrobe_category == "Sweater"


def _prefer(
    pool: HybridPool,
    chooser: random.Random,
    accepted: set[str],
    predicate: Callable[[PoolItem], bool],
    *,
    prefer_thick: bool = False,
    prefer_waterproof: bool = False,
) -> PoolItem | None:
    """Choose one pool item, preferring a name the stylist accepted."""
    options = [item for item in pool.items if predicate(item)]
    if prefer_waterproof:
        waterproof = [item for item in options if item.waterproof]
        if waterproof:
            options = waterproof
    if prefer_thick:
        thick = [item for item in options if item.thickness in {"Thick", "Thermal"}]
        if thick:
            options = thick
    if not options:
        return None
    preferred = [item for item in options if item.name in accepted]
    source = preferred if preferred else options
    if len(source) == 1:
        return source[0]
    return chooser.choice(source)


def _image_url(garment: OwnedGarment) -> str | None:
    """Return a stored image link when the row has one."""
    raw = getattr(garment, "image_url", None)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text if text != "" else None


def _payload(item: PoolItem, *, removable: bool = False) -> dict[str, object]:
    """Copy one pool item into the recommendation garment shape."""
    body: dict[str, object] = {"id": item.item_id, "label": item.name, "category": item.category}
    if item.image_url is not None:
        body["image_url"] = item.image_url
    if removable:
        body["removable"] = True
    return body

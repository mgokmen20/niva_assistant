"""Named constants for the Niva thermal decision engine.

Calculation code must reference these names. Do not copy the numbers into
services or route handlers.

The temperature bands follow the Universal Thermal Climate Index (UTCI)
stress categories used for outdoor exposure. Wearer preference is bounded
the way ASHRAE Standard 55 treats comfort as an individual condition, not a
single fixed temperature. Age offsets stand in for pediatric thermoregulation
(higher surface-area-to-mass ratio and faster cooling) and geriatric
thermoregulation (blunted cold perception). Clothing records are layered
ensembles in the sense of ISO 9920 (base, mid, outer, plus accessories).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class ThermalStressCategory(StrEnum):
    """UTCI-based stress band for an effective temperature."""

    EXTREME_HEAT = "EXTREME_HEAT"
    MODERATE_HEAT = "MODERATE_HEAT"
    COMFORT = "COMFORT"
    SLIGHT_COLD = "SLIGHT_COLD"
    MODERATE_COLD = "MODERATE_COLD"
    EXTREME_COLD = "EXTREME_COLD"


# UTCI thresholds in degrees Celsius.
# EXTREME_HEAT is strictly above EXTREME_HEAT_C.
# EXTREME_COLD is strictly below EXTREME_COLD_C.
# Shared edges belong to the warmer band: 9.0 is comfort, 0.0 is slight
# cold, and -13.0 is moderate cold. The open interval (26.0, 32.0] is
# UTCI moderate heat stress.
EXTREME_HEAT_C: Final[float] = 32.0
COMFORT_MIN_C: Final[float] = 9.0
COMFORT_MAX_C: Final[float] = 26.0
SLIGHT_COLD_MIN_C: Final[float] = 0.0
SLIGHT_COLD_MAX_C: Final[float] = 9.0
MODERATE_COLD_MIN_C: Final[float] = -13.0
MODERATE_COLD_MAX_C: Final[float] = 0.0
EXTREME_COLD_C: Final[float] = -13.0

# European outdoor clothing bands on the effective temperature. These are
# narrower than the UTCI comfort window, which runs from 9 °C to 26 °C and
# would otherwise dress a chilly day in a T-shirt. Freezing is strictly
# below 5 °C. Chilly runs up to but not including 13 °C (5.0 through 12.9).
# Mild runs up to but not including 19 °C. Warm runs up to but not including
# 24 °C. Hot is 24 °C and above.
CLOTHING_FREEZING_BELOW_C: Final[float] = 5.0
CLOTHING_CHILLY_BELOW_C: Final[float] = 13.0
CLOTHING_MILD_BELOW_C: Final[float] = 19.0
CLOTHING_WARM_BELOW_C: Final[float] = 24.0


class ClothingBand(StrEnum):
    """Outdoor layering band for an effective temperature."""

    FREEZING = "FREEZING"
    CHILLY = "CHILLY"
    MILD = "MILD"
    WARM = "WARM"
    HOT = "HOT"


# Age bands for cold-offset compensation. A child is strictly under
# AGE_CHILD_THRESHOLD. A senior is at or above AGE_SENIOR_THRESHOLD.
AGE_CHILD_THRESHOLD: Final[int] = 12
AGE_SENIOR_THRESHOLD: Final[int] = 65
SENIOR_COLD_OFFSET_CELSIUS: Final[float] = 2.0
CHILD_COLD_OFFSET_CELSIUS: Final[float] = 1.0

# Wearer feedback applied as a personal comfort offset (ASHRAE 55).
FEEDBACK_STEP_CELSIUS: Final[float] = 0.5
FEEDBACK_MIN_OFFSET: Final[float] = -5.0
FEEDBACK_MAX_OFFSET: Final[float] = 5.0

# Adaptive calibration from the latest ratings. A cold rating lowers the
# decision temperature so the next outfit is warmer. A warm rating raises
# it. Perfect ratings ease the running offset back toward zero.
CALIBRATION_HISTORY_LIMIT: Final[int] = 10
CALIBRATION_COLD_STEP_CELSIUS: Final[float] = -FEEDBACK_STEP_CELSIUS
CALIBRATION_WARM_STEP_CELSIUS: Final[float] = FEEDBACK_STEP_CELSIUS
CALIBRATION_PERFECT_PULL_CELSIUS: Final[float] = FEEDBACK_STEP_CELSIUS / 2.0
CALIBRATION_MIN_OFFSET_CELSIUS: Final[float] = -3.0
CALIBRATION_MAX_OFFSET_CELSIUS: Final[float] = 3.0

# Starting comfort offset chosen at registration, before any feedback.
THERMAL_PREFERENCE_COLD_SENSITIVE: Final[str] = "cold_sensitive"
THERMAL_PREFERENCE_BALANCED: Final[str] = "balanced"
THERMAL_PREFERENCE_WARM_SENSITIVE: Final[str] = "warm_sensitive"
BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS: Final[float] = -1.5
BASELINE_OFFSET_BALANCED_CELSIUS: Final[float] = 0.0
BASELINE_OFFSET_WARM_SENSITIVE_CELSIUS: Final[float] = 1.5
ENVIRONMENT_MOSTLY_INDOOR: Final[str] = "mostly_indoor"
ENVIRONMENT_MOSTLY_OUTDOOR: Final[str] = "mostly_outdoor"

# Interface languages. German is Swiss High German and is stored as "de".
PREFERRED_LANGUAGE_EN: Final[str] = "en"
PREFERRED_LANGUAGE_DE: Final[str] = "de"
PREFERRED_LANGUAGE_TR: Final[str] = "tr"
ALLOWED_PREFERRED_LANGUAGES: Final[frozenset[str]] = frozenset(
    {PREFERRED_LANGUAGE_EN, PREFERRED_LANGUAGE_DE, PREFERRED_LANGUAGE_TR}
)

# Account roles. Public registration always stores ROLE_USER.
ROLE_USER: Final[str] = "user"
ROLE_PARTNER: Final[str] = "partner"
ROLE_ADMIN: Final[str] = "admin"
ALLOWED_ROLES: Final[frozenset[str]] = frozenset({ROLE_USER, ROLE_PARTNER, ROLE_ADMIN})

# Remember-me sessions stay valid after the browser is closed.
REMEMBER_ME_EXPIRE_DAYS: Final[int] = 30

# Admin user list. The cap keeps one query from scanning the whole table.
ADMIN_USER_PAGE_SIZE_DEFAULT: Final[int] = 20
ADMIN_USER_PAGE_SIZE_MAX: Final[int] = 100

# Analytics windows and effective-temperature buckets. Edges are inclusive
# on the warmer side of each closed band: 5.0 and 10.0 are "5-10°C",
# 15.0 is "11-15°C", and anything above 15.0 is ">15°C". Values between
# 10.0 and 11.0 stay in "11-15°C" so no temperature is dropped.
ANALYTICS_DEFAULT_DAYS: Final[int] = 7
ANALYTICS_DISTRIBUTION_DAYS: Final[int] = 30
ANALYTICS_MAX_DAYS: Final[int] = 365
ANALYTICS_TEMP_COLD_BELOW_C: Final[float] = 5.0
ANALYTICS_TEMP_COOL_MAX_C: Final[float] = 10.0
ANALYTICS_TEMP_MILD_MAX_C: Final[float] = 15.0
ANALYTICS_BUCKET_BELOW_5: Final[str] = "<5°C"
ANALYTICS_BUCKET_5_TO_10: Final[str] = "5-10°C"
ANALYTICS_BUCKET_11_TO_15: Final[str] = "11-15°C"
ANALYTICS_BUCKET_ABOVE_15: Final[str] = ">15°C"
ANALYTICS_RATING_TOO_COLD: Final[str] = "TOO_COLD"
ANALYTICS_RATING_PERFECT: Final[str] = "PERFECT"
ANALYTICS_RATING_TOO_WARM: Final[str] = "TOO_WARM"
ANALYTICS_SENTIMENT_TOO_COLD: Final[str] = "too_cold"
ANALYTICS_SENTIMENT_PERFECT: Final[str] = "perfect"
ANALYTICS_SENTIMENT_TOO_WARM: Final[str] = "too_warm"
ANALYTICS_LAYER_WINTER_COAT: Final[str] = "winter_coat"
ANALYTICS_LAYER_LIGHT_JACKET: Final[str] = "light_jacket"
ANALYTICS_LAYER_FLEECE: Final[str] = "fleece"
ANALYTICS_LAYER_T_SHIRT: Final[str] = "t_shirt"
# Named age choices for the workspace storage card. The purge API accepts
# any boundary date; these are the presets the interface offers.
PURGE_AGE_DAY_CHOICES: Final[tuple[int, ...]] = (30, 60, 90)

# Activity preference around the calibrated decision temperature.
# Light (walking) raises it. Warm (sitting still) lowers it.
OUTFIT_PREFERENCE_SHIFT_CELSIUS: Final[float] = 2.0
OUTFIT_PREFERENCE_BALANCED: Final[str] = "balanced"
OUTFIT_PREFERENCE_LIGHT: Final[str] = "light"
OUTFIT_PREFERENCE_WARM: Final[str] = "warm"
OUTFIT_PREFERENCE_AUTO: Final[str] = "auto"

# Keyless neural voices, one per wearer language. Swiss German uses de-CH.
# tr-TR-AhmetNeural is listed by Edge but currently returns no audio, so
# Turkish uses Emel, which does synthesize.
DEFAULT_NEURAL_VOICE: Final[str] = "en-US-ChristopherNeural"
TURKISH_NEURAL_VOICE: Final[str] = "tr-TR-EmelNeural"
GERMAN_NEURAL_VOICE: Final[str] = "de-CH-JanNeural"
SPEECH_TEXT_MAX_LENGTH: Final[int] = 4000
VOICE_QUESTION_MAX_LENGTH: Final[int] = 500
CHAT_ANSWER_MAX_SENTENCES: Final[int] = 2
LLAMA_CHAT_MODEL: Final[str] = "@cf/meta/llama-3.1-8b-instruct"
LLAMA_CHAT_TIMEOUT_SECONDS: Final[float] = 12.0

# Accessory and shell triggers. UV 3 is the WHO lower bound for adult eye
# protection. Children use a lower trigger because pediatric skin burns
# sooner. Wind at Beaufort 4 (5.5 m/s) justifies a shell or extremity
# cover when the ensemble would otherwise be air-permeable.
# 15 percent, or a WMO code of drizzle and above, is enough to pack rain gear.
RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT: Final[float] = 15.0
WMO_PRECIPITATION_CODE_MIN: Final[int] = 51
UV_PROTECTION_MIN_INDEX: Final[float] = 3.0
CHILD_UV_PROTECTION_MIN_INDEX: Final[float] = 2.5
WIND_SHELL_MIN_MPS: Final[float] = 5.5

# Trip packing uses the coldest night and the wettest day in the span.
# Fleece uses its own cut. The coat still follows the freezing clothing
# band, and sunglasses follow the adult UV trigger.
# Precipitation is tiered so a low chance does not add a rain jacket:
# below 20 percent adds nothing, 20 up to 40 percent adds a compact
# umbrella only, and 40 percent or a WMO drizzle/snow code adds both
# a waterproof shell and an umbrella.
FORECAST_DAY_COUNT: Final[int] = 7
# Local hours used to compare the same day's morning, afternoon, and evening.
DIURNAL_MORNING_HOUR: Final[int] = 8
DIURNAL_AFTERNOON_HOUR: Final[int] = 14
DIURNAL_EVENING_HOUR: Final[int] = 20
# A day that moves by this much needs a layer the wearer can take off.
DIURNAL_SWING_MIN_CELSIUS: Final[float] = 6.0
TRAVEL_MAX_DAYS: Final[int] = 16
TRAVEL_FLEECE_BELOW_C: Final[float] = 12.0
TRAVEL_UMBRELLA_MIN_PERCENT: Final[float] = 20.0
TRAVEL_SHELL_MIN_PERCENT: Final[float] = 40.0
TRAVEL_CLEAR_WEATHER_CODES: Final[frozenset[int]] = frozenset({0, 1})
TRAVEL_SNOW_WEATHER_CODES: Final[frozenset[int]] = frozenset({71, 73, 75, 77, 85, 86})

PROBABILITY_MIN_PERCENT: Final[float] = 0.0
PROBABILITY_MAX_PERCENT: Final[float] = 100.0
UV_INDEX_MIN: Final[float] = 0.0
WIND_SPEED_MIN_MPS: Final[float] = 0.0
AGE_MIN_YEARS: Final[int] = 0


class ClothingCategory(StrEnum):
    """ISO 9920 layer slot for a garment or carried item."""

    BASE = "BASE"
    MID = "MID"
    OUTER = "OUTER"
    ACCESSORY = "ACCESSORY"


@dataclass(frozen=True, slots=True)
class ClothingItem:
    """One standard garment or accessory the engine may recommend."""

    id: str
    label: str
    category: ClothingCategory


LIGHT_T_SHIRT: Final[ClothingItem] = ClothingItem(
    "light_t_shirt",
    "Light T-shirt",
    ClothingCategory.BASE,
)
LONG_SLEEVE_BASE: Final[ClothingItem] = ClothingItem(
    "long_sleeve_base",
    "Long-sleeve base layer",
    ClothingCategory.BASE,
)
THERMAL_BASE_LAYER: Final[ClothingItem] = ClothingItem(
    "thermal_base_layer",
    "Thermal base layer",
    ClothingCategory.BASE,
)
LIGHT_OVERSHIRT: Final[ClothingItem] = ClothingItem(
    "light_overshirt",
    "Light overshirt",
    ClothingCategory.MID,
)
ZIP_HOODIE: Final[ClothingItem] = ClothingItem(
    "zip_hoodie",
    "Zip hoodie",
    ClothingCategory.MID,
)
CARDIGAN: Final[ClothingItem] = ClothingItem(
    "cardigan",
    "Cardigan",
    ClothingCategory.MID,
)
FLEECE_MID_LAYER: Final[ClothingItem] = ClothingItem(
    "fleece_mid_layer",
    "Fleece mid-layer",
    ClothingCategory.MID,
)
INSULATED_MID_LAYER: Final[ClothingItem] = ClothingItem(
    "insulated_mid_layer",
    "Insulated mid-layer",
    ClothingCategory.MID,
)
WIND_SHELL: Final[ClothingItem] = ClothingItem(
    "wind_shell",
    "Wind shell",
    ClothingCategory.OUTER,
)
LIGHT_JACKET: Final[ClothingItem] = ClothingItem(
    "light_jacket",
    "Light jacket",
    ClothingCategory.OUTER,
)
WATERPROOF_SHELL: Final[ClothingItem] = ClothingItem(
    "waterproof_shell",
    "Waterproof shell",
    ClothingCategory.OUTER,
)
WINTER_COAT: Final[ClothingItem] = ClothingItem(
    "winter_coat",
    "Winter coat",
    ClothingCategory.OUTER,
)
UMBRELLA: Final[ClothingItem] = ClothingItem(
    "umbrella",
    "Umbrella",
    ClothingCategory.ACCESSORY,
)
SUNGLASSES: Final[ClothingItem] = ClothingItem(
    "sunglasses",
    "Sunglasses",
    ClothingCategory.ACCESSORY,
)
WARM_HAT: Final[ClothingItem] = ClothingItem(
    "warm_hat",
    "Warm hat",
    ClothingCategory.ACCESSORY,
)
GLOVES: Final[ClothingItem] = ClothingItem(
    "gloves",
    "Gloves",
    ClothingCategory.ACCESSORY,
)
SCARF: Final[ClothingItem] = ClothingItem(
    "scarf",
    "Scarf",
    ClothingCategory.ACCESSORY,
)
SUN_HAT: Final[ClothingItem] = ClothingItem(
    "sun_hat",
    "Sun hat",
    ClothingCategory.ACCESSORY,
)

STANDARD_CLOTHING_ITEMS: Final[tuple[ClothingItem, ...]] = (
    LIGHT_T_SHIRT,
    LONG_SLEEVE_BASE,
    THERMAL_BASE_LAYER,
    LIGHT_OVERSHIRT,
    ZIP_HOODIE,
    CARDIGAN,
    FLEECE_MID_LAYER,
    INSULATED_MID_LAYER,
    WIND_SHELL,
    LIGHT_JACKET,
    WATERPROOF_SHELL,
    WINTER_COAT,
    UMBRELLA,
    SUNGLASSES,
    WARM_HAT,
    GLOVES,
    SCARF,
    SUN_HAT,
)

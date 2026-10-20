"""Recommendation strategies: deterministic rules and Cloudflare Clef.

Clef is called only when both Cloudflare credentials are present. Any
timeout or HTTP error status falls back to the rule engine. Credential
values are sent on the Authorization header and are not written to logs.
"""

import logging
from datetime import datetime
from typing import Any, Final
from urllib.parse import quote

import httpx

from ..core.config import Settings, cloudflare_credentials_configured, get_settings
from ..core.constants import (
    AGE_CHILD_THRESHOLD,
    RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT,
    STANDARD_CLOTHING_ITEMS,
    WIND_SHELL_MIN_MPS,
    ClothingCategory,
    ClothingItem,
    ThermalStressCategory,
)
from ..domain.interfaces import IRecommendationProvider
from ..domain.thermal_engine import (
    ThermalInput,
    calculate_effective_temperature,
    classify_utci_stress,
    determine_clothing_layers,
)

logger = logging.getLogger(__name__)

CLEF_MODEL_NAME: Final[str] = "@cf/cloudflare/clef"
CLEF_MODEL_SELECTOR: Final[str] = "clef"
CLEF_REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0
CLEF_RUN_URL: Final[str] = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/clef"
)
NONE_LAYER_ID: Final[str] = "none"
NOUL_YES_MIN_PROBABILITY: Final[float] = 0.5
RISK_LEVEL_LOW: Final[str] = "low"
RISK_LEVEL_MODERATE: Final[str] = "moderate"
RISK_LEVEL_HIGH: Final[str] = "high"
RISK_LEVEL_EXTREME: Final[str] = "extreme"
ALLOWED_RISK_LEVELS: Final[frozenset[str]] = frozenset(
    {RISK_LEVEL_LOW, RISK_LEVEL_MODERATE, RISK_LEVEL_HIGH, RISK_LEVEL_EXTREME}
)
REMOVABLE_MID_LAYER_IDS: Final[frozenset[str]] = frozenset(
    {"light_overshirt", "cardigan", "zip_hoodie"}
)
RISK_LEVEL_BY_UTCI_CATEGORY: Final[dict[ThermalStressCategory, str]] = {
    ThermalStressCategory.COMFORT: RISK_LEVEL_LOW,
    ThermalStressCategory.SLIGHT_COLD: RISK_LEVEL_LOW,
    ThermalStressCategory.MODERATE_HEAT: RISK_LEVEL_MODERATE,
    ThermalStressCategory.MODERATE_COLD: RISK_LEVEL_MODERATE,
    ThermalStressCategory.EXTREME_HEAT: RISK_LEVEL_HIGH,
    ThermalStressCategory.EXTREME_COLD: RISK_LEVEL_HIGH,
}
_CLOTHING_BY_ID: Final[dict[str, ClothingItem]] = {
    item.id: item for item in STANDARD_CLOTHING_ITEMS
}
# Local clock bands for the spoken greeting. Evening covers late night.
VOICE_MORNING_START_HOUR: Final[int] = 5
VOICE_AFTERNOON_START_HOUR: Final[int] = 12
VOICE_EVENING_START_HOUR: Final[int] = 17
ACCESSORY_WARNINGS: Final[dict[str, str]] = {
    "umbrella": "Don't forget an umbrella!",
    "warm_hat": "Keep a beanie handy.",
    "beanie": "Keep a beanie handy.",
    "gloves": "Don't forget your gloves.",
    "scarf": "A scarf is worth keeping close.",
    "sunglasses": "Sunglasses would be wise in this light.",
    "sun_hat": "A sun hat will help.",
}


def build_voice_summary(
    recommendation: dict[str, Any],
    *,
    first_name: str | None = None,
    city_name: str | None = None,
    air_temperature_celsius: float | None = None,
    effective_temperature_celsius: float | None = None,
    rain_probability_percent: float | None = None,
    wind_speed_mps: float | None = None,
    local_hour: int | None = None,
    outfit_preference: str | None = None,
) -> str:
    """Build a spoken assistant script from layers and the current place.

    A signed-in wearer is greeted by the time of day and first name.
    A guest hears "Hello there!". Weather and layering follow in prose.
    Accessory lines are added only when that item was selected.
    """
    hour = local_hour if local_hour is not None else datetime.now().hour
    sentences = [_greeting(first_name, hour)]
    if air_temperature_celsius is not None:
        feels_like = (
            effective_temperature_celsius
            if effective_temperature_celsius is not None
            else air_temperature_celsius
        )
        sentences.append(
            _weather_sentence(
                city_name,
                air_temperature_celsius,
                feels_like,
                rain_probability_percent if rain_probability_percent is not None else 0.0,
                wind_speed_mps if wind_speed_mps is not None else 0.0,
            )
        )
    layering = _layering_sentence(recommendation)
    if layering is not None:
        sentences.append(layering)
    sentences.extend(_accessory_warnings(recommendation))
    preference_line = _preference_sentence(outfit_preference)
    if preference_line is not None:
        sentences.append(preference_line)
    return " ".join(sentences)


def local_hour_from_weather(raw_weather: dict[str, Any]) -> int:
    """Read the hour from an Open-Meteo local timestamp, or the server clock."""
    current = raw_weather.get("current")
    if isinstance(current, dict):
        stamp = current.get("time")
        if isinstance(stamp, str) and "T" in stamp:
            hour_text = stamp.split("T", 1)[1][:2]
            if hour_text.isdigit():
                hour = int(hour_text)
                if 0 <= hour <= 23:
                    return hour
    return datetime.now().hour


def _preference_sentence(outfit_preference: str | None) -> str | None:
    """Describe why the spoken outfit matches the selected preference."""
    if outfit_preference == "light":
        return "This lighter outfit is for walking and activity."
    if outfit_preference == "warm":
        return "This warmer outfit adds insulation for staying still."
    return None


def _greeting(first_name: str | None, hour: int) -> str:
    """Return a time-of-day greeting, or a guest hello when no name is known."""
    name = first_name.strip() if isinstance(first_name, str) else ""
    if name == "":
        return "Hello there!"
    if VOICE_MORNING_START_HOUR <= hour < VOICE_AFTERNOON_START_HOUR:
        salutation = "Good morning"
    elif VOICE_AFTERNOON_START_HOUR <= hour < VOICE_EVENING_START_HOUR:
        salutation = "Good afternoon"
    else:
        salutation = "Good evening"
    return f"{salutation} {name}!"


def _weather_sentence(
    city_name: str | None,
    air_temperature_celsius: float,
    effective_temperature_celsius: float,
    rain_probability_percent: float,
    wind_speed_mps: float,
) -> str:
    """Name both the air temperature and the feels-like temperature.

    The feels-like value is the effective temperature used for clothing,
    so the spoken summary matches the number on the outfit card.
    """
    sky = _sky_phrase(rain_probability_percent, wind_speed_mps)
    air = _format_celsius(air_temperature_celsius)
    feels = _format_celsius(effective_temperature_celsius)
    city = city_name.strip() if isinstance(city_name, str) else ""
    if city != "":
        return (
            f"In {city}, the air temperature is {air}°C, "
            f"but it feels like {feels}°C with {sky} today."
        )
    return (
        f"The air temperature is {air}°C, "
        f"but it feels like {feels}°C with {sky} today."
    )


def _sky_phrase(rain_probability_percent: float, wind_speed_mps: float) -> str:
    """Pick the spoken sky phrase from the same rain and wind triggers as the engine."""
    rainy = rain_probability_percent >= RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT
    gusty = wind_speed_mps >= WIND_SHELL_MIN_MPS
    if rainy and gusty:
        return "light rain and gusty winds"
    if rainy:
        return "light rain"
    if gusty:
        return "gusty winds"
    return "clear skies"


def _format_celsius(value: float) -> str:
    """Render a temperature without a trailing decimal when it is whole."""
    rounded = round(float(value), 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _layering_sentence(recommendation: dict[str, Any]) -> str | None:
    """Turn selected layers into one recommendation sentence."""
    pieces: list[str] = []
    base = _layer_label(recommendation.get("base_layer"))
    mid = _layer_label(recommendation.get("mid_layer"))
    outer = _layer_label(recommendation.get("outer_layer"))
    if base is not None:
        pieces.append(f"starting with your {base}")
    if mid is not None:
        pieces.append(f"adding {_article(mid)} {mid}")
    if outer is not None:
        pieces.append(f"grabbing your {outer}")
    if not pieces:
        return None
    if len(pieces) == 1:
        joined = pieces[0]
    elif len(pieces) == 2:
        joined = f"{pieces[0]} and {pieces[1]}"
    else:
        joined = f"{pieces[0]}, {pieces[1]}, and {pieces[2]}"
    return f"I recommend {joined} before heading out."


def _accessory_warnings(recommendation: dict[str, Any]) -> list[str]:
    """Return short reminders for accessories the outfit includes."""
    accessories = recommendation.get("accessories")
    if not isinstance(accessories, list):
        return []
    warnings: list[str] = []
    for item in accessories:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id in ACCESSORY_WARNINGS:
            warnings.append(ACCESSORY_WARNINGS[item_id])
    return warnings


def _layer_label(layer: Any) -> str | None:
    """Return a spoken garment label, or None when the slot is empty."""
    if not isinstance(layer, dict):
        return None
    label = layer.get("label")
    if not isinstance(label, str) or label.strip() == "":
        return None
    return _spoken(label)


def _article(phrase: str) -> str:
    """Choose 'a' or 'an' from the first letter of a spoken garment name."""
    if phrase[:1].lower() in "aeiou":
        return "an"
    return "a"


def _spoken(label: str) -> str:
    """Return a label whose first character is lowercase for a spoken sentence."""
    if label == "":
        return label
    return label[0].lower() + label[1:]


def _criteria_for(category: ClothingCategory) -> dict[str, str]:
    """Return Clef choice criteria for one clothing slot."""
    return {
        item.id: item.label
        for item in STANDARD_CLOTHING_ITEMS
        if item.category is category
    }


def _optional_slot_criteria(category: ClothingCategory) -> dict[str, str]:
    """Return slot criteria plus an explicit option for wearing nothing there."""
    criteria = _criteria_for(category)
    criteria[NONE_LAYER_ID] = "No garment in this slot."
    return criteria


_CLEF_BAND_GUIDANCE: Final[str] = (
    " Use the effective temperature. Below 5°C: thermal base, insulated mid layer, winter coat, "
    "warm hat, scarf, and gloves. From 5°C through 12.9°C: long-sleeve base, fleece or knit mid "
    "layer, and a light jacket or windbreaker; mid and outer must not be none. From 13°C through "
    "18.9°C: light T-shirt plus a light jacket or cardigan. From 19°C through 23.9°C: light "
    "T-shirt, and mid and outer are none unless it is raining or windy. At 24°C and above: light "
    "T-shirt, mid and outer are none, and sunglasses are recommended."
)


def _clef_questions() -> dict[str, dict[str, Any]]:
    """Build the Clef question schema for layers, accessories, and risk."""
    questions: dict[str, dict[str, Any]] = {
        "base_layer": {
            "type": "choice",
            "instructions": "Which base layer should the wearer put on?" + _CLEF_BAND_GUIDANCE,
            "criteria": _criteria_for(ClothingCategory.BASE),
        },
        "mid_layer": {
            "type": "choice",
            "instructions": "Which mid layer should the wearer add, if any?" + _CLEF_BAND_GUIDANCE,
            "criteria": _optional_slot_criteria(ClothingCategory.MID),
        },
        "outer_layer": {
            "type": "choice",
            "instructions": "Which outer layer should the wearer add, if any?" + _CLEF_BAND_GUIDANCE,
            "criteria": _optional_slot_criteria(ClothingCategory.OUTER),
        },
        "risk_level": {
            "type": "choice",
            "instructions": "What thermal risk does this outdoor exposure pose?",
            "criteria": {
                RISK_LEVEL_LOW: "Little stress. Ordinary clothing is enough.",
                RISK_LEVEL_MODERATE: "Noticeable heat or cold. Extra care is warranted.",
                RISK_LEVEL_HIGH: "Strong heat or cold. Protective clothing should stay on outdoors.",
                RISK_LEVEL_EXTREME: "Dangerous heat or cold. Limit time outdoors.",
            },
        },
    }
    for item in STANDARD_CLOTHING_ITEMS:
        if item.category is not ClothingCategory.ACCESSORY:
            continue
        questions[item.id] = {
            "type": "noul",
            "instructions": f"Should the wearer bring {item.label}?",
        }
    return questions


def _clef_state(thermal_input: ThermalInput, raw_weather: dict[str, Any]) -> dict[str, Any]:
    """Format the observation Clef evaluates. Credentials are not included."""
    current = raw_weather.get("current")
    return {
        "air_temp_celsius": thermal_input.air_temp,
        "feels_like_celsius": thermal_input.feels_like,
        "wind_speed_metres_per_second": thermal_input.wind_speed,
        "rain_probability_percent": thermal_input.rain_prob,
        "uv_index": thermal_input.uv_index,
        "age_years": thermal_input.age,
        "personal_offset_celsius": thermal_input.personal_offset,
        "current_weather": current if isinstance(current, dict) else {},
    }


def _layer_payload(item: ClothingItem, removable: bool | None = None) -> dict[str, Any]:
    """Copy a catalog item into the recommendation dictionary."""
    payload: dict[str, Any] = {
        "id": item.id,
        "label": item.label,
        "category": item.category.value,
    }
    if removable is not None:
        payload["removable"] = removable
    return payload


def _mid_is_removable(item_id: str, age: int) -> bool:
    """Return whether a chosen mid layer should be marked removable."""
    if age < AGE_CHILD_THRESHOLD:
        return True
    return item_id in REMOVABLE_MID_LAYER_IDS


class RuleBasedRecommendationProvider(IRecommendationProvider):
    """Select clothing with the deterministic thermal engine."""

    async def generate_recommendation(
        self,
        thermal_input: ThermalInput,
        raw_weather: dict[str, Any],
    ) -> dict[str, Any]:
        """Return layers from the clothing band, age, and the wearer offset.

        ``raw_weather`` supplies the local hour for the spoken greeting.
        Clothing still comes from ``thermal_input``.

        Args:
            thermal_input: Domain observation for this request.
            raw_weather: Original forecast body. Used for the local hour.

        Returns:
            Layers, accessories, UTCI category, risk level, and voice summary.
        """
        effective_temperature = calculate_effective_temperature(
            feels_like=thermal_input.feels_like,
            age=thermal_input.age,
            personal_offset=thermal_input.personal_offset,
        )
        category = classify_utci_stress(effective_temperature)
        layers = determine_clothing_layers(
            effective_temp=effective_temperature,
            wind_speed=thermal_input.wind_speed,
            rain_prob=thermal_input.rain_prob,
            uv_index=thermal_input.uv_index,
            age=thermal_input.age,
            weather_code=thermal_input.weather_code,
        )
        recommendation: dict[str, Any] = {
            "provider": "rule_based",
            "effective_temperature_celsius": effective_temperature,
            "utci_category": category.value,
            "risk_level": RISK_LEVEL_BY_UTCI_CATEGORY[category],
            "base_layer": layers["base_layer"],
            "mid_layer": layers["mid_layer"],
            "outer_layer": layers["outer_layer"],
            "accessories": layers["accessories"],
        }
        recommendation["voice_summary"] = _summary_for_observation(
            recommendation,
            thermal_input,
            raw_weather,
        )
        return recommendation


class ClefRecommendationProvider(IRecommendationProvider):
    """Ask Cloudflare Clef for a structured clothing decision.

    Missing credentials skip the network call. A timeout or an HTTP error
    status logs a warning and returns the rule-based recommendation.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Store settings and an optional HTTP client.

        Args:
            settings: Application settings. Loaded from the environment
                when omitted.
            client: Async client to reuse. The provider does not close a
                client it did not create.
        """
        self._settings = settings if settings is not None else get_settings()
        self._client = client
        self._fallback = RuleBasedRecommendationProvider()

    async def generate_recommendation(
        self,
        thermal_input: ThermalInput,
        raw_weather: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a Clef decision, or the rule-based payload when Clef cannot run.

        Args:
            thermal_input: Domain observation for this request.
            raw_weather: Forecast body included in the Clef state.

        Returns:
            The same payload shape as the rule-based provider.
        """
        if not cloudflare_credentials_configured(self._settings):
            logger.info(
                "Cloudflare Clef credentials are not configured. "
                "Using the rule-based recommendation."
            )
            return await self._fallback.generate_recommendation(thermal_input, raw_weather)
        try:
            response = await self._post(thermal_input, raw_weather)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException:
            logger.warning("Cloudflare Clef timed out. Using the rule-based recommendation.")
            return await self._fallback.generate_recommendation(thermal_input, raw_weather)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Cloudflare Clef returned HTTP %s. Using the rule-based recommendation.",
                exc.response.status_code,
            )
            return await self._fallback.generate_recommendation(thermal_input, raw_weather)
        except httpx.RequestError:
            logger.warning(
                "Cloudflare Clef could not be reached. Using the rule-based recommendation."
            )
            return await self._fallback.generate_recommendation(thermal_input, raw_weather)
        except ValueError:
            logger.warning(
                "Cloudflare Clef returned a body that is not JSON. "
                "Using the rule-based recommendation."
            )
            return await self._fallback.generate_recommendation(thermal_input, raw_weather)
        if not isinstance(payload, dict) or payload.get("success") is False:
            logger.warning(
                "Cloudflare Clef reported an unsuccessful result. "
                "Using the rule-based recommendation."
            )
            return await self._fallback.generate_recommendation(thermal_input, raw_weather)
        try:
            return _recommendation_from_clef(payload, thermal_input)
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "Cloudflare Clef response could not be parsed. "
                "Using the rule-based recommendation."
            )
            return await self._fallback.generate_recommendation(thermal_input, raw_weather)

    async def _post(
        self,
        thermal_input: ThermalInput,
        raw_weather: dict[str, Any],
    ) -> httpx.Response:
        """POST the Clef state and questions to Workers AI."""
        account_id = quote(self._settings.CLOUDFLARE_ACCOUNT_ID.strip(), safe="")
        token = self._settings.CLOUDFLARE_API_TOKEN.strip()
        url = CLEF_RUN_URL.format(account_id=account_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "model": CLEF_MODEL_SELECTOR,
            "state": _clef_state(thermal_input, raw_weather),
            "questions": _clef_questions(),
        }
        if self._client is not None:
            return await self._client.post(
                url,
                headers=headers,
                json=body,
                timeout=CLEF_REQUEST_TIMEOUT_SECONDS,
            )
        async with httpx.AsyncClient() as client:
            return await client.post(
                url,
                headers=headers,
                json=body,
                timeout=CLEF_REQUEST_TIMEOUT_SECONDS,
            )


def _recommendation_from_clef(
    payload: dict[str, Any],
    thermal_input: ThermalInput,
) -> dict[str, Any]:
    """Map a Workers AI Clef body onto the recommendation dictionary."""
    result = payload.get("result")
    model_body = result if isinstance(result, dict) else payload
    answers = model_body.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("Clef response is missing answers.")
    effective_temperature = calculate_effective_temperature(
        feels_like=thermal_input.feels_like,
        age=thermal_input.age,
        personal_offset=thermal_input.personal_offset,
    )
    category = classify_utci_stress(effective_temperature)
    recommendation: dict[str, Any] = {
        "provider": "clef",
        "effective_temperature_celsius": effective_temperature,
        "utci_category": category.value,
        "risk_level": _choice(answers, "risk_level", ALLOWED_RISK_LEVELS),
        "base_layer": _garment_choice(answers, "base_layer", ClothingCategory.BASE, required=True),
        "mid_layer": _mid_choice(answers, thermal_input.age),
        "outer_layer": _garment_choice(answers, "outer_layer", ClothingCategory.OUTER, required=False),
        "accessories": _accessory_choices(answers),
    }
    recommendation["voice_summary"] = _summary_for_observation(recommendation, thermal_input, {})
    return recommendation


def _summary_for_observation(
    recommendation: dict[str, Any],
    thermal_input: ThermalInput,
    raw_weather: dict[str, Any],
) -> str:
    """Speak the outfit for this observation before a name or city is known."""
    return build_voice_summary(
        recommendation,
        air_temperature_celsius=thermal_input.air_temp,
        effective_temperature_celsius=float(recommendation["effective_temperature_celsius"]),
        rain_probability_percent=thermal_input.rain_prob,
        wind_speed_mps=thermal_input.wind_speed,
        local_hour=local_hour_from_weather(raw_weather),
    )


def _choice(answers: dict[str, Any], question_id: str, allowed: frozenset[str]) -> str:
    """Return a Clef choice when it is one of the allowed option ids."""
    answer = answers.get(question_id)
    if not isinstance(answer, dict):
        raise ValueError(f"Clef answer for {question_id} is missing.")
    chosen = answer.get("choice")
    if not isinstance(chosen, str) or chosen not in allowed:
        raise ValueError(f"Clef choice for {question_id} is not allowed.")
    return chosen


def _garment_choice(
    answers: dict[str, Any],
    question_id: str,
    category: ClothingCategory,
    *,
    required: bool,
) -> dict[str, Any] | None:
    """Resolve a layer choice to a catalog item, or None when the slot is empty."""
    allowed = frozenset(_criteria_for(category))
    if not required:
        allowed = allowed | {NONE_LAYER_ID}
    chosen = _choice(answers, question_id, allowed)
    if chosen == NONE_LAYER_ID:
        return None
    item = _CLOTHING_BY_ID[chosen]
    return _layer_payload(item)


def _mid_choice(answers: dict[str, Any], age: int) -> dict[str, Any] | None:
    """Resolve the mid-layer choice and its removable flag."""
    layer = _garment_choice(answers, "mid_layer", ClothingCategory.MID, required=False)
    if layer is None:
        return None
    layer["removable"] = _mid_is_removable(str(layer["id"]), age)
    return layer


def _accessory_choices(answers: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect accessories whose noul probability is at least the yes threshold."""
    selected: list[dict[str, Any]] = []
    for item in STANDARD_CLOTHING_ITEMS:
        if item.category is not ClothingCategory.ACCESSORY:
            continue
        answer = answers.get(item.id)
        if not isinstance(answer, dict) or "noul" not in answer:
            raise ValueError(f"Clef answer for {item.id} is missing.")
        probability = answer["noul"]
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError(f"Clef noul for {item.id} is not a probability.")
        if float(probability) >= NOUL_YES_MIN_PROBABILITY:
            selected.append(_layer_payload(item))
    return selected

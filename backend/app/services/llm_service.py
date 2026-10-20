"""Cloudflare Workers AI outfit summary in the wearer's language.

The thermal engine still chooses the garments. This module only explains
that choice in two short sentences. Missing credentials, a failed model
call, or a reply in the wrong language keep a deterministic sentence.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import quote
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, cloudflare_credentials_configured
from ..core.constants import (
    CALIBRATION_HISTORY_LIMIT,
    ENVIRONMENT_MOSTLY_OUTDOOR,
    LLAMA_CHAT_MODEL,
    LLAMA_CHAT_TIMEOUT_SECONDS,
    PREFERRED_LANGUAGE_DE,
    PREFERRED_LANGUAGE_EN,
    PREFERRED_LANGUAGE_TR,
    WIND_SHELL_MIN_MPS,
)
from ..models.recommendation import FeedbackEntry
from ..models.user import User
from .diurnal import diurnal_context_lines
from .tts_service import normalize_language

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPTS: Final[dict[str, str]] = {
    PREFERRED_LANGUAGE_TR: (
        "Sen Niva adında samimi ve pratik bir termal giyim asistanısın. "
        "Kullanıcıya seçilen şehir ve sıcaklık için önerilen kıyafet katmanlarını "
        "doğal, sıcak ve motive edici bir Türkçe ile 2 kısa cümlede özetle."
    ),
    PREFERRED_LANGUAGE_DE: (
        "Du bist Niva, ein freundlicher Begleiter für thermischen Komfort. "
        "Fasse die empfohlenen Kleidungsschichten auf Schweizer Hochdeutsch "
        "(ohne ß, stattdessen ss) in 2 kurzen Sätzen zusammen."
    ),
    PREFERRED_LANGUAGE_EN: (
        "You are Niva, an empathetic companion for thermal comfort. "
        "Summarize the recommended clothing layers naturally in 2 short sentences."
    ),
}
LLAMA_RUN_URL: Final[str] = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/" + LLAMA_CHAT_MODEL
)
_SENTENCE_SPLIT: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")
_SUMMARY_SENTENCES: Final[int] = 2


@dataclass(frozen=True)
class WearerDecisionContext:
    """Facts the summary agent may use to explain the outfit."""

    personal_offset_celsius: float
    environment_routine: str | None
    recent_ratings: tuple[str, ...]


async def load_wearer_decision_context(
    user_id: UUID,
    db: AsyncSession,
    personal_offset_celsius: float,
) -> WearerDecisionContext:
    """Read routine and recent ratings for the spoken explanation.

    The offset is the value already applied to the clothing decision.
    A missing wearer leaves the routine empty and the ratings empty.
    """
    routine_row = await db.execute(
        select(User.environment_routine).where(User.id == user_id)
    )
    routine = routine_row.scalar_one_or_none()
    rating_row = await db.execute(
        select(FeedbackEntry.thermal_rating)
        .where(FeedbackEntry.user_id == user_id)
        .order_by(FeedbackEntry.created_at.desc(), FeedbackEntry.id.desc())
        .limit(CALIBRATION_HISTORY_LIMIT)
    )
    newest_first = [str(rating) for rating in rating_row.scalars().all()]
    stored_routine = routine if isinstance(routine, str) and routine.strip() != "" else None
    return WearerDecisionContext(
        personal_offset_celsius=personal_offset_celsius,
        environment_routine=stored_routine,
        recent_ratings=tuple(reversed(newest_first)),
    )


TRAVEL_GARMENT_NAMES: dict[str, dict[str, str]] = {
    "base_shirt": {
        PREFERRED_LANGUAGE_EN: "T-shirt / Base layer",
        PREFERRED_LANGUAGE_DE: "T-Shirt / Basisschicht",
        PREFERRED_LANGUAGE_TR: "Tişört / İç katman",
    },
    "fleece": {
        PREFERRED_LANGUAGE_EN: "Fleece mid-layer",
        PREFERRED_LANGUAGE_DE: "Fleece",
        PREFERRED_LANGUAGE_TR: "Polar",
    },
    "light_jacket": {
        PREFERRED_LANGUAGE_EN: "Light jacket",
        PREFERRED_LANGUAGE_DE: "Leichte Jacke",
        PREFERRED_LANGUAGE_TR: "Hafif ceket",
    },
    "winter_coat": {
        PREFERRED_LANGUAGE_EN: "Winter coat",
        PREFERRED_LANGUAGE_DE: "Wintermantel",
        PREFERRED_LANGUAGE_TR: "Kışlık mont",
    },
    "waterproof_shell": {
        PREFERRED_LANGUAGE_EN: "Waterproof rain shell",
        PREFERRED_LANGUAGE_DE: "Wasserdichte Regenjacke",
        PREFERRED_LANGUAGE_TR: "Su geçirmez yağmurluk",
    },
    "umbrella": {
        PREFERRED_LANGUAGE_EN: "Compact umbrella",
        PREFERRED_LANGUAGE_DE: "Kompakter Regenschirm",
        PREFERRED_LANGUAGE_TR: "Kompakt şemsiye",
    },
    "sunglasses": {
        PREFERRED_LANGUAGE_EN: "Sunglasses",
        PREFERRED_LANGUAGE_DE: "Sonnenbrille",
        PREFERRED_LANGUAGE_TR: "Güneş gözlüğü",
    },
}


def garment_display_name(item_id: str, language: str) -> str:
    """Return a spoken garment name for ``language``, never a raw id."""
    selected = normalize_language(language)
    names = TRAVEL_GARMENT_NAMES.get(item_id)
    if names is None:
        return item_id.replace("_", " ")
    return names.get(selected, names[PREFERRED_LANGUAGE_EN])


def system_prompt_for(language: str) -> str:
    """Return the Workers AI system prompt for ``language``."""
    return SUMMARY_SYSTEM_PROMPTS[normalize_language(language)]


def _rain_gear_selected(recommendation: dict[str, Any]) -> bool:
    """True when the outfit already includes an umbrella or a waterproof shell."""
    outer = recommendation.get("outer_layer")
    outer_id = outer.get("id") if isinstance(outer, dict) else ""
    if outer_id in {"waterproof_shell", "umbrella"}:
        return True
    accessories = recommendation.get("accessories")
    if not isinstance(accessories, list):
        return False
    return any(isinstance(item, dict) and item.get("id") in {"waterproof_shell", "umbrella"} for item in accessories)


def build_decision_context(
    *,
    language: str,
    city_name: str | None,
    air_temperature_celsius: float,
    effective_temperature_celsius: float,
    wind_speed_mps: float,
    rain_probability_percent: float,
    recommendation: dict[str, Any],
    wearer: WearerDecisionContext | None,
) -> str:
    """Describe the outfit decision for the model user message.

    The facts stay in English. The system prompt requires the reply language.
    """
    offset = 0.0 if wearer is None else wearer.personal_offset_celsius
    routine = "unknown" if wearer is None or wearer.environment_routine is None else wearer.environment_routine
    ratings = "none" if wearer is None or not wearer.recent_ratings else ", ".join(wearer.recent_ratings)
    city = city_name.strip() if isinstance(city_name, str) and city_name.strip() != "" else "unknown"
    lines = [
        f"Reply language: {normalize_language(language)}",
        "Write exactly 2 short sentences in that language only.",
        "Explain why this outfit was selected. Use the temperature offset, "
        "daily routine, wind, and recent feedback when they are present.",
        f"City: {city}",
        f"Air temperature C: {air_temperature_celsius:.1f}",
        f"Feels-like temperature C: {effective_temperature_celsius:.1f}",
        f"Wind m/s: {wind_speed_mps:.1f}",
        f"Rain probability percent: {rain_probability_percent:.0f}",
        f"Personal temperature offset delta T C: {offset:+.1f}",
        f"Daily routine: {routine}",
        f"Recent thermal feedback oldest first: {ratings}",
        f"Base layer: {_layer_label(recommendation.get('base_layer'))}",
        f"Mid layer: {_layer_label(recommendation.get('mid_layer'))}",
        f"Outer layer: {_layer_label(recommendation.get('outer_layer'))}",
        f"Accessories: {_accessory_labels(recommendation)}",
    ]
    if _rain_gear_selected(recommendation):
        lines.append("Rain was detected. Mention the umbrella and the waterproof shell.")
    stored_periods = recommendation.get("diurnal")
    if isinstance(stored_periods, list):
        lines.extend(diurnal_context_lines(stored_periods))
    return "\n".join(lines)


async def compose_voice_summary(
    *,
    language: str,
    english_summary: str,
    recommendation: dict[str, Any],
    city_name: str | None,
    air_temperature_celsius: float,
    effective_temperature_celsius: float,
    wind_speed_mps: float,
    rain_probability_percent: float,
    wearer: WearerDecisionContext | None,
    settings: Settings | None,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Return a two-sentence summary in ``language``.

    English without a model reply keeps ``english_summary``, which is the
    deterministic script. German and Turkish always leave that script.
    """
    selected = normalize_language(language)
    model_text = await request_outfit_summary(
        language=selected,
        context=build_decision_context(
            language=selected,
            city_name=city_name,
            air_temperature_celsius=air_temperature_celsius,
            effective_temperature_celsius=effective_temperature_celsius,
            wind_speed_mps=wind_speed_mps,
            rain_probability_percent=rain_probability_percent,
            recommendation=recommendation,
            wearer=wearer,
        ),
        settings=settings,
        http_client=http_client,
    )
    if model_text is not None:
        cleaned = _limit_sentences(_swiss_spelling(model_text) if selected == PREFERRED_LANGUAGE_DE else model_text)
        if cleaned != "" and _reply_language_ok(cleaned, selected):
            return cleaned
    if selected == PREFERRED_LANGUAGE_EN:
        return english_summary
    return fallback_summary(
        language=selected,
        city_name=city_name,
        air_temperature_celsius=air_temperature_celsius,
        effective_temperature_celsius=effective_temperature_celsius,
        wind_speed_mps=wind_speed_mps,
        recommendation=recommendation,
        wearer=wearer,
    )


async def _post(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    http_client: httpx.AsyncClient | None,
) -> httpx.Response:
    """POST one Workers AI chat request."""
    if http_client is not None:
        return await http_client.post(
            url,
            headers=headers,
            json=body,
            timeout=LLAMA_CHAT_TIMEOUT_SECONDS,
        )
    async with httpx.AsyncClient() as client:
        return await client.post(
            url,
            headers=headers,
            json=body,
            timeout=LLAMA_CHAT_TIMEOUT_SECONDS,
        )


async def request_outfit_summary(
    *,
    language: str,
    context: str,
    settings: Settings | None,
    http_client: httpx.AsyncClient | None = None,
    system_prompt: str | None = None,
) -> str | None:
    """Ask Llama for a short explanation, or return None to use the fallback.

    ``system_prompt`` replaces the clothing prompt when a caller such as
    the travel planner needs a different two-sentence brief.
    """
    if settings is None or not cloudflare_credentials_configured(settings):
        return None
    account_id = quote(settings.CLOUDFLARE_ACCOUNT_ID.strip(), safe="")
    token = settings.CLOUDFLARE_API_TOKEN.strip()
    url = LLAMA_RUN_URL.format(account_id=account_id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    prompt = system_prompt if system_prompt is not None and system_prompt.strip() != "" else system_prompt_for(language)
    body = {
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ]
    }
    try:
        response = await _post(url, headers, body, http_client)
        response.raise_for_status()
        payload = response.json()
    except (httpx.TimeoutException, httpx.HTTPError, ValueError):
        logger.warning("Cloudflare outfit summary could not be completed.")
        return None
    if not isinstance(payload, dict) or payload.get("success") is False:
        logger.warning("Cloudflare outfit summary reported an unsuccessful result.")
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    reply = result.get("response")
    if not isinstance(reply, str) or reply.strip() == "":
        return None
    return reply.strip()


def fallback_summary(
    *,
    language: str,
    city_name: str | None,
    air_temperature_celsius: float,
    effective_temperature_celsius: float,
    wind_speed_mps: float,
    recommendation: dict[str, Any],
    wearer: WearerDecisionContext | None,
) -> str:
    """Explain the outfit in two sentences without calling a model."""
    selected = normalize_language(language)
    air = _format_celsius(air_temperature_celsius)
    feels = _format_celsius(effective_temperature_celsius)
    place = city_name.strip() if isinstance(city_name, str) and city_name.strip() != "" else ""
    windy = wind_speed_mps >= WIND_SHELL_MIN_MPS
    offset = 0.0 if wearer is None else wearer.personal_offset_celsius
    outdoor = wearer is not None and wearer.environment_routine == ENVIRONMENT_MOSTLY_OUTDOOR
    outer_layer = recommendation.get("outer_layer")
    outer_id = outer_layer.get("id") if isinstance(outer_layer, dict) else ""
    outer_id = outer_id if isinstance(outer_id, str) else ""
    outer = _layer_label(outer_layer)
    if selected == PREFERRED_LANGUAGE_TR:
        return _turkish_fallback(place, air, feels, windy, outer_id, outer, offset, outdoor)
    if selected == PREFERRED_LANGUAGE_DE:
        return _german_fallback(place, air, feels, windy, outer_id, outer, offset, outdoor)
    return _english_fallback(place, air, feels, windy, outer, offset, outdoor)


def _turkish_outer(item_id: str, label: str) -> str:
    """Return a spoken Turkish name for the selected outer garment."""
    names = {
        "light_jacket": "hafif ceketini",
        "wind_shell": "rüzgarlığını",
        "waterproof_shell": "yağmurluğunu",
        "winter_coat": "kış montunu",
    }
    return names.get(item_id, label)


def _german_outer(item_id: str, label: str) -> str:
    """Return a spoken Swiss German name for the selected outer garment."""
    names = {
        "light_jacket": "eine leichte Jacke",
        "wind_shell": "eine Windjacke",
        "waterproof_shell": "eine Regenjacke",
        "winter_coat": "einen Wintermantel",
    }
    return names.get(item_id, label)


def _turkish_fallback(
    place: str,
    air: str,
    feels: str,
    windy: bool,
    outer_id: str,
    outer: str,
    offset: float,
    outdoor: bool,
) -> str:
    """Two Turkish sentences. Wind is mentioned only when it is strong."""
    where = f"{place} için " if place != "" else ""
    spoken_outer = _turkish_outer(outer_id, outer)
    if windy and outer != "none":
        first = f"{air}°C olmasına rağmen biraz rüzgar olduğu için {spoken_outer} de almanı önerdim."
    else:
        first = f"{where}hava {air}°C, hissedilen ise {feels}°C."
    routine = "Günün çoğunu dışarıda geçirdiğin için " if outdoor else ""
    second = f"{routine}konfor farkın {offset:+.1f}°C olduğu için kombin buna göre ayarlandı."
    return f"{first} {second}"


def _german_fallback(
    place: str,
    air: str,
    feels: str,
    windy: bool,
    outer_id: str,
    outer: str,
    offset: float,
    outdoor: bool,
) -> str:
    """Two Swiss German sentences. The letter ß is not used."""
    where = f"In {place} " if place != "" else ""
    spoken_outer = _german_outer(outer_id, outer)
    if windy and outer != "none":
        first = (
            f"{where}sind es {air}°C, gefühlt {feels}°C, und es ist etwas windig, "
            f"deshalb nimm auch {spoken_outer} mit."
        )
    else:
        first = f"{where}sind es {air}°C und es fühlt sich wie {feels}°C an."
    routine = "Du bist meist draussen und " if outdoor else ""
    second = (
        f"{routine}dein Temperaturausgleich liegt bei {offset:+.1f}°C, "
        f"deshalb ist die Aussenschicht {spoken_outer}."
    )
    return _swiss_spelling(f"{first} {second}")


def _english_fallback(
    place: str,
    air: str,
    feels: str,
    windy: bool,
    outer: str,
    offset: float,
    outdoor: bool,
) -> str:
    """Two English sentences used when the model reply is unusable."""
    where = f"In {place}, " if place != "" else ""
    if windy and outer != "none":
        first = (
            f"{where}it is {air}°C and feels like {feels}°C, with a breeze, "
            f"so I included {outer}."
        )
    else:
        first = f"{where}it is {air}°C and feels like {feels}°C."
    routine = "You spend most of the day outdoors, and " if outdoor else ""
    second = f"{routine}your comfort offset is {offset:+.1f}°C, so the outer layer is {outer}."
    return f"{first} {second}"


def _layer_label(layer: object) -> str:
    """Return a garment label, or ``none`` when that slot is empty."""
    if not isinstance(layer, dict):
        return "none"
    label = layer.get("label")
    if isinstance(label, str) and label.strip() != "":
        return label.strip()
    return "none"


def _accessory_labels(recommendation: dict[str, Any]) -> str:
    """Join accessory labels, or ``none`` when the list is empty."""
    accessories = recommendation.get("accessories")
    if not isinstance(accessories, list):
        return "none"
    labels = [_layer_label(item) for item in accessories]
    names = [label for label in labels if label != "none"]
    return ", ".join(names) if names else "none"


def _format_celsius(value: float) -> str:
    """Format a temperature without a trailing .0."""
    rounded = round(value, 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


def _limit_sentences(text: str) -> str:
    """Keep the first two sentences."""
    cleaned = " ".join(text.split())
    parts = [part for part in _SENTENCE_SPLIT.split(cleaned) if part]
    if not parts:
        return cleaned
    return " ".join(parts[:_SUMMARY_SENTENCES])


def _swiss_spelling(text: str) -> str:
    """Replace ß with ss for Swiss High German."""
    return text.replace("ß", "ss").replace("ẞ", "SS")


def _reply_language_ok(text: str, language: str) -> bool:
    """Reject a model reply that is clearly in another language."""
    sample = text.casefold()
    turkish_marks = any(character in text for character in "ğĞşŞıİçÇöÖüÜ")
    if language == PREFERRED_LANGUAGE_TR:
        return turkish_marks or any(word in sample.split() for word in ("için", "hava", "katman", "ceket"))
    if language == PREFERRED_LANGUAGE_DE:
        return "ß" not in text and any(
            word in sample.split() for word in ("und", "ist", "sind", "deshalb", "nimm", "outfit")
        )
    english_marks = any(word in sample.split() for word in ("the", "and", "it", "your", "so", "with"))
    return english_marks and not turkish_marks

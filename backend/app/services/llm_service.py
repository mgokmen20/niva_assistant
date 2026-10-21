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
from .tts_service import normalize_language

logger = logging.getLogger(__name__)

LLAMA_RUN_URL: Final[str] = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/" + LLAMA_CHAT_MODEL
)
_SENTENCE_SPLIT: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")
_SUMMARY_SENTENCES: Final[int] = 2
_PROMPT_INJECTION: Final[re.Pattern[str]] = re.compile(
    r"```+"
    r"|\[/?INST\]"
    r"|<\|im_start\|>"
    r"|<\|im_end\|>"
    r"|###\s*instruction"
    r"|###\s*response"
    r"|\b(?:system|human|assistant|user)\s*:",
    re.IGNORECASE,
)


def strip_prompt_delimiters(value: str) -> str:
    """Remove chat-role markers without joining separate lines."""
    return _PROMPT_INJECTION.sub(" ", value).replace("`", " ")


def sanitize_prompt_text(value: str) -> str:
    """Remove prompt-injection markers from wearer text.

    Role labels, instruction fences, and backticks are dropped.
    Line breaks in a longer context are kept.
    """
    cleaned = strip_prompt_delimiters(value)
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line != "").strip()


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
    """Return the briefing prompt when no outfit or weather was supplied."""
    from .ai_service import summary_system_prompt

    return summary_system_prompt(
        language=language,
        weather_progression="Not provided.",
        selected_items="No clothing selected.",
    )


def build_decision_context(
    *,
    language: str,
    city_name: str | None,
    air_temperature_celsius: float,
    effective_temperature_celsius: float,
    wind_speed_mps: float,
    rain_probability_percent: float,
    recommendation: dict[str, Any],
    user_name: str | None = None,
) -> str:
    """List the briefing facts for the model user message.

    The facts stay in English. The system prompt requires the reply language.
    Routine and comfort history stay out, so the reply cannot invent a reason.
    """
    city = city_name.strip() if isinstance(city_name, str) and city_name.strip() != "" else "unknown"
    name = user_name.strip() if isinstance(user_name, str) and user_name.strip() != "" else "unknown"
    from .ai_service import selected_outfit_text, weather_progression_text

    outfit = selected_outfit_text(recommendation)
    progression = weather_progression_text(
        recommendation,
        air_temperature_celsius=air_temperature_celsius,
        effective_temperature_celsius=effective_temperature_celsius,
    )
    lines = [
        f"Reply language: {normalize_language(language)}",
        "Write only the greeting, the weather, and the selected outfit.",
        f"User name: {name}",
        f"Location: {city}",
        f"Air temperature C: {air_temperature_celsius:.1f}",
        f"Feels-like temperature C: {effective_temperature_celsius:.1f}",
        f"Wind m/s: {wind_speed_mps:.1f}",
        f"Rain probability percent: {rain_probability_percent:.0f}",
        f"Weather progression: {progression}",
        f"Selected outfit: {outfit}",
        "Do not mention activities, routines, or why the clothes were chosen.",
    ]
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
    user_name: str | None = None,
) -> str:
    """Return a short briefing in ``language``.

    English without a model reply keeps ``english_summary``, which is the
    deterministic script. German and Turkish always leave that script.
    """
    from .ai_service import selected_outfit_text, summary_system_prompt, weather_progression_text

    selected = normalize_language(language)
    place = city_name.strip() if isinstance(city_name, str) else ""
    name = user_name.strip() if isinstance(user_name, str) else ""
    context = build_decision_context(
        language=selected,
        city_name=city_name,
        air_temperature_celsius=air_temperature_celsius,
        effective_temperature_celsius=effective_temperature_celsius,
        wind_speed_mps=wind_speed_mps,
        rain_probability_percent=rain_probability_percent,
        recommendation=recommendation,
        user_name=name,
    )
    model_text = await request_model_reply(
        system_prompt=summary_system_prompt(
            language=selected,
            weather_progression=weather_progression_text(
                recommendation,
                air_temperature_celsius=air_temperature_celsius,
                effective_temperature_celsius=effective_temperature_celsius,
            ),
            selected_items=selected_outfit_text(recommendation),
            user_name=name,
            location=place,
        ),
        user_content=context,
        settings=settings,
        http_client=http_client,
    )
    if model_text is not None:
        cleaned = _swiss_spelling(model_text) if selected == PREFERRED_LANGUAGE_DE else model_text.strip()
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


async def request_model_reply(
    *,
    system_prompt: str,
    user_content: str,
    settings: Settings | None,
    http_client: httpx.AsyncClient | None = None,
) -> str | None:
    """Ask Llama for a raw reply.

    The text is not trimmed to two sentences. Callers that need a short
    briefing apply that limit themselves. Missing credentials, a failed
    request, or an empty reply return None.
    """
    if settings is None or not cloudflare_credentials_configured(settings):
        return None
    account_id = quote(settings.CLOUDFLARE_ACCOUNT_ID.strip(), safe="")
    token = settings.CLOUDFLARE_API_TOKEN.strip()
    url = LLAMA_RUN_URL.format(account_id=account_id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": strip_prompt_delimiters(user_content)},
        ]
    }
    try:
        response = await _post(url, headers, body, http_client)
        response.raise_for_status()
        payload = response.json()
    except (httpx.TimeoutException, httpx.HTTPError, ValueError):
        logger.warning("Cloudflare text generation could not be completed.")
        return None
    if not isinstance(payload, dict) or payload.get("success") is False:
        logger.warning("Cloudflare text generation reported an unsuccessful result.")
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    reply = result.get("response")
    if not isinstance(reply, str) or reply.strip() == "":
        return None
    return reply.strip()


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
    prompt = system_prompt if system_prompt is not None and system_prompt.strip() != "" else system_prompt_for(language)
    reply = await request_model_reply(
        system_prompt=prompt,
        user_content=context,
        settings=settings,
        http_client=http_client,
    )
    if reply is None:
        return None
    return _limit_sentences(reply)


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
        text = _turkish_fallback(place, air, feels, windy, outer_id, outer, offset, outdoor)
    elif selected == PREFERRED_LANGUAGE_DE:
        text = _german_fallback(place, air, feels, windy, outer_id, outer, offset, outdoor)
    else:
        text = _english_fallback(place, air, feels, windy, outer, offset, outdoor)
    return _append_selected_pieces(text, recommendation, selected)


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


def _wardrobe_names(recommendation: dict[str, Any]) -> str:
    """Join the hybrid stylist's accepted item names."""
    selection = recommendation.get("wardrobe_selection")
    if not isinstance(selection, list):
        return ""
    names = [name.strip() for name in selection if isinstance(name, str) and name.strip() != ""]
    return ", ".join(names)


def _append_selected_pieces(text: str, recommendation: dict[str, Any], language: str) -> str:
    """Add the chosen item names to a deterministic briefing."""
    names = _wardrobe_names(recommendation)
    if names == "":
        return text
    if language == PREFERRED_LANGUAGE_TR:
        return f"{text} Seçilen parçalar: {names}."
    if language == PREFERRED_LANGUAGE_DE:
        return _swiss_spelling(f"{text} Ausgewählt: {names}.")
    return f"{text} Today's pieces are {names}."


def _layer_label(layer: object) -> str:
    """Return a garment label, or ``none`` when that slot is empty."""
    if not isinstance(layer, dict):
        return "none"
    label = layer.get("label")
    if isinstance(label, str) and label.strip() != "":
        return label.strip()
    return "none"


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

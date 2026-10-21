"""Answer a spoken weather question in the wearer's language.

Cloudflare Workers AI writes the reply when credentials are configured.
A timeout, a network error, or missing credentials falls back to a short
deterministic sentence built from the current outfit and weather. Edge TTS
then speaks that sentence.
"""

import base64
import logging
import re
from typing import Any, Final
from urllib.parse import quote
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, cloudflare_credentials_configured, get_settings
from ..core.constants import (
    CHAT_ANSWER_MAX_SENTENCES,
    LLAMA_CHAT_MODEL,
    LLAMA_CHAT_TIMEOUT_SECONDS,
    RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT,
    WIND_SHELL_MIN_MPS,
)
from ..core.exceptions import VoiceUnavailableError
from ..models.user import User
from .diurnal import diurnal_context_lines
from .llm_service import sanitize_prompt_text
from .calibration import calculate_user_thermal_offset, wearer_age_years
from .llm_service import sanitize_prompt_text, strip_prompt_delimiters
from .recommendation_service import RecommendationService
from .tts_service import normalize_language, voice_for_language
from .voice import generate_speech_audio

logger = logging.getLogger(__name__)

NIVA_CHAT_SYSTEM_PROMPT: Final[str] = (
    "You are Niva, a smart personal thermal & clothing assistant. "
    "Answer the user in the EXACT SAME language they used (English, German, Turkish, etc.). "
    "Limit your answer strictly to 1 or 2 concise, conversational, friendly sentences. "
    "Base your answer strictly on the provided context: current weather, effective temperature, "
    "recommended clothing layers, and user thermal offset. Do not hallucinate outside conditions. "
    "CRITICAL RULE - LANGUAGE MIRRORING: You MUST reply in the EXACT SAME language as the user "
    "question. If the user asks in English (\"How is the weather today\"), you MUST answer in "
    "English. If in Turkish, answer in Turkish. If in German, answer in German. Never switch "
    "languages. Place names such as Biel/Bienne, Bern, or Switzerland do not choose the language. "
    "MANDATORY CLOTHING CONSISTENCY: Your outfit advice must match the recommendation cards 1:1. "
    "Never drop or skip any recommended accessory (such as warm hat, beanie, or umbrella) if it "
    "is present in the context. "
    "PHYSICAL LAYER BANDS on the effective feels-like temperature, after wind chill "
    "and the wearer's calibration offset: below 5°C use a thermal or long-sleeve base, "
    "a heavy fleece or insulated mid layer, a winter coat, a warm hat, a scarf, and gloves. "
    "From 5°C through 12.9°C use a long-sleeve base, a fleece or warm knit mid layer, and a "
    "light jacket, trench, or windbreaker. In that band the mid layer and the outer layer are "
    "both required; never say either is not needed. From 13°C through 18.9°C use a T-shirt or "
    "casual shirt plus a light jacket or cardigan. From 19°C through 23.9°C use a T-shirt and "
    "say the mid and outer layers are not needed unless it is raining or windy. At 24°C and "
    "above use a light breathable T-shirt, say the mid and outer layers are not needed, and "
    "recommend sunglasses. If the recommendation context lists specific garments, name those "
    "garments and do not substitute a different band. "
    "For outfit/weather questions, provide a complete 2-sentence response: (1) Greeting with "
    "user's name, city and current weather, (2) Complete list of clothing layers INCLUDING all "
    "accessories. "
    "Use natural terminology in the target language (e.g. Turkish: \"uzun kollu içlik/tişört, "
    "polar ara katman, hafif ceket ve bere\"; do not use hybrid terms like \"temel layer\"). "
    "When stating the temperature, ALWAYS mention both the air temperature "
    "({air_temperature}°C) and the effective feels-like temperature "
    "({effective_temperature}°C) together. For example: \"The air temperature is 11.1°C, "
    "feeling like 9.7°C\". Never quote only one number without clarifying whether it is "
    "air temperature or feels-like temperature. "
    "Turkish temperature clause: \"Hava sıcaklığı {air}°C, hissedilen ise {eff}°C.\" "
    "German temperature clause: \"Die Lufttemperatur beträgt {air}°C, gefühlt sind es {eff}°C.\""
)
LLAMA_RUN_URL: Final[str] = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"
    "@cf/meta/llama-3.1-8b-instruct"
)
LANGUAGE_ENGLISH: Final[str] = "en"
LANGUAGE_GERMAN: Final[str] = "de"
LANGUAGE_TURKISH: Final[str] = "tr"
_TURKISH_MARKERS: Final[frozenset[str]] = frozenset("ğĞşŞıİçÇ")
_GERMAN_MARKERS: Final[frozenset[str]] = frozenset("äÄß")
_TURKISH_WORDS: Final[frozenset[str]] = frozenset(
    {
        "bir",
        "bugun",
        "bugün",
        "bu",
        "çok",
        "cok",
        "değil",
        "degil",
        "dışarı",
        "disari",
        "evet",
        "giy",
        "giymeliyim",
        "hava",
        "için",
        "icin",
        "mı",
        "mi",
        "mu",
        "mü",
        "ne",
        "rüzgar",
        "ruzgar",
        "şemsiye",
        "semsiye",
        "ve",
        "yağmur",
        "yagmur",
    }
)
_GERMAN_WORDS: Final[frozenset[str]] = frozenset(
    {
        "brauchst",
        "das",
        "der",
        "die",
        "draussen",
        "draußen",
        "ein",
        "es",
        "heute",
        "ich",
        "ist",
        "kalt",
        "nicht",
        "regenschirm",
        "regen",
        "und",
        "wetter",
        "wie",
        "wind",
    }
)
_ENGLISH_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "do",
        "how",
        "i",
        "is",
        "need",
        "should",
        "the",
        "today",
        "wear",
        "weather",
        "what",
    }
)
# Place names are removed before language scoring so a Swiss city cannot
# switch an English question into German or French.
_PLACE_WORDS: Final[frozenset[str]] = frozenset(
    {
        "basel",
        "bern",
        "biel",
        "bienne",
        "geneva",
        "geneve",
        "genf",
        "isvicre",
        "isviçre",
        "lausanne",
        "lucerne",
        "luzern",
        "munsingen",
        "münsingen",
        "schweiz",
        "suisse",
        "svizzera",
        "switzerland",
        "zuerich",
        "zurich",
        "zürich",
    }
)
_SENTENCE_SPLIT: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")
_WORD_SPLIT: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+", re.UNICODE)
_LANGUAGE_NAMES: Final[dict[str, str]] = {
    LANGUAGE_ENGLISH: "English",
    LANGUAGE_GERMAN: "German",
    LANGUAGE_TURKISH: "Turkish",
}
# Spoken names stay in the reply language. English uses the catalog label.
_LOCAL_GARMENT_NAMES: Final[dict[str, dict[str, str]]] = {
    "light_t_shirt": {LANGUAGE_GERMAN: "T-Shirt", LANGUAGE_TURKISH: "tişört"},
    "long_sleeve_base": {LANGUAGE_GERMAN: "Langarmshirt", LANGUAGE_TURKISH: "uzun kollu içlik"},
    "thermal_base_layer": {LANGUAGE_GERMAN: "Thermo-Unterwäsche", LANGUAGE_TURKISH: "termal içlik"},
    "light_overshirt": {LANGUAGE_GERMAN: "leichtes Overshirt", LANGUAGE_TURKISH: "ince gömlek"},
    "zip_hoodie": {LANGUAGE_GERMAN: "Kapuzenjacke", LANGUAGE_TURKISH: "fermuarlı sweatshirt"},
    "cardigan": {LANGUAGE_GERMAN: "Strickjacke", LANGUAGE_TURKISH: "hırka"},
    "fleece_mid_layer": {LANGUAGE_GERMAN: "Fleece-Zwischenschicht", LANGUAGE_TURKISH: "polar ara katman"},
    "insulated_mid_layer": {LANGUAGE_GERMAN: "isolierte Zwischenschicht", LANGUAGE_TURKISH: "yalıtımlı ara katman"},
    "wind_shell": {LANGUAGE_GERMAN: "Windjacke", LANGUAGE_TURKISH: "rüzgarlık"},
    "light_jacket": {LANGUAGE_GERMAN: "leichte Jacke", LANGUAGE_TURKISH: "hafif ceket"},
    "waterproof_shell": {LANGUAGE_GERMAN: "Regenjacke", LANGUAGE_TURKISH: "yağmurluk"},
    "winter_coat": {LANGUAGE_GERMAN: "Wintermantel", LANGUAGE_TURKISH: "kış montu"},
    "umbrella": {LANGUAGE_GERMAN: "Regenschirm", LANGUAGE_TURKISH: "şemsiye"},
    "sunglasses": {LANGUAGE_GERMAN: "Sonnenbrille", LANGUAGE_TURKISH: "güneş gözlüğü"},
    "warm_hat": {LANGUAGE_GERMAN: "Mütze", LANGUAGE_TURKISH: "bere"},
    "gloves": {LANGUAGE_GERMAN: "Handschuhe", LANGUAGE_TURKISH: "eldiven"},
    "scarf": {LANGUAGE_GERMAN: "Schal", LANGUAGE_TURKISH: "atkı"},
    "sun_hat": {LANGUAGE_GERMAN: "Sonnenhut", LANGUAGE_TURKISH: "güneş şapkası"},
}


def _strip_places(text: str, city_name: str | None = None) -> str:
    """Remove place names so they cannot decide the reply language."""
    cleaned = text.strip()
    blocked = set(_PLACE_WORDS)
    if isinstance(city_name, str):
        for part in re.split(r"[\s,/;]+", city_name):
            token = part.strip().casefold()
            if token != "":
                blocked.add(token)
    words = _WORD_SPLIT.findall(cleaned)
    kept = [word for word in words if word.casefold() not in blocked]
    return " ".join(kept)


def detect_reply_language(text: str, city_name: str | None = None) -> str:
    """Return ``tr``, ``de``, or ``en`` for a question or reply.

    Turkish-only letters win first, then the language with the most
    function words. Place names, including the active city, are ignored.
    Anything else is English.

    Args:
        text: Sentence whose language should be identified.
        city_name: Active place. Its tokens are not treated as language cues.

    Returns:
        A two-letter language code.
    """
    sample = _strip_places(text, city_name)
    if any(character in sample for character in _TURKISH_MARKERS):
        return LANGUAGE_TURKISH
    if any(character in sample for character in _GERMAN_MARKERS):
        return LANGUAGE_GERMAN
    words = {match.casefold() for match in _WORD_SPLIT.findall(sample)}
    scores = {
        LANGUAGE_TURKISH: len(words & _TURKISH_WORDS),
        LANGUAGE_GERMAN: len(words & _GERMAN_WORDS),
        LANGUAGE_ENGLISH: len(words & _ENGLISH_WORDS),
    }
    best = max(scores.values())
    if best == 0:
        return LANGUAGE_ENGLISH
    if scores[LANGUAGE_TURKISH] == best and scores[LANGUAGE_TURKISH] > scores[LANGUAGE_GERMAN]:
        return LANGUAGE_TURKISH
    if scores[LANGUAGE_GERMAN] == best and scores[LANGUAGE_GERMAN] > scores[LANGUAGE_ENGLISH]:
        return LANGUAGE_GERMAN
    if scores[LANGUAGE_ENGLISH] == best:
        return LANGUAGE_ENGLISH
    if scores[LANGUAGE_GERMAN] == best:
        return LANGUAGE_GERMAN
    return LANGUAGE_ENGLISH


def limit_sentences(text: str, maximum: int = CHAT_ANSWER_MAX_SENTENCES) -> str:
    """Keep at most ``maximum`` sentences from ``text``."""
    cleaned = " ".join(text.split())
    if cleaned == "":
        return ""
    parts = [part for part in _SENTENCE_SPLIT.split(cleaned) if part]
    if not parts:
        return cleaned
    return " ".join(parts[:maximum])


def _reply_matches_cards(
    answer: str,
    question: str,
    city_name: str,
    recommendation: dict[str, Any],
) -> bool:
    """Return whether ``answer`` keeps the question language and every garment.

    A reply that switches language, or that omits a card layer or accessory,
    is rejected so the spoken outfit cannot drift from the cards.
    """
    language = detect_reply_language(question, city_name)
    if detect_reply_language(answer, city_name) != language:
        return False
    folded = answer.casefold()
    for item_id, label in _outfit_items(recommendation):
        spoken = _localized_name(item_id, label, language).casefold()
        if spoken not in folded:
            return False
    return True


def _garment_fields(layer: object) -> tuple[str, str] | None:
    """Return ``(id, english label)`` for one clothing dictionary."""
    if not isinstance(layer, dict):
        return None
    label = layer.get("label")
    if not isinstance(label, str) or label.strip() == "":
        return None
    item_id = layer.get("id")
    identifier = item_id.strip() if isinstance(item_id, str) else ""
    return identifier, label.strip()


def _outfit_items(recommendation: dict[str, Any]) -> list[tuple[str, str]]:
    """Return tops, the bottom, outerwear, then every accessory."""
    items: list[tuple[str, str]] = []
    tops = recommendation.get("tops")
    if isinstance(tops, list):
        for item in tops:
            fields = _garment_fields(item)
            if fields is not None:
                items.append(fields)
        for key in ("bottom", "outerwear"):
            fields = _garment_fields(recommendation.get(key))
            if fields is not None:
                items.append(fields)
    else:
        for key in ("base_layer", "mid_layer", "outer_layer"):
            fields = _garment_fields(recommendation.get(key))
            if fields is not None:
                items.append(fields)
    accessories = recommendation.get("accessories")
    if isinstance(accessories, list):
        for item in accessories:
            fields = _garment_fields(item)
            if fields is not None:
                items.append(fields)
    return items


def _localized_name(item_id: str, english_label: str, language: str) -> str:
    """Return a natural garment name in ``language``."""
    names = _LOCAL_GARMENT_NAMES.get(item_id, {})
    translated = names.get(language)
    if isinstance(translated, str) and translated.strip() != "":
        return translated
    return english_label


def _join_names(names: list[str], language: str) -> str:
    """Join garment names with the conjunction used in ``language``."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if language == LANGUAGE_TURKISH:
        conjunction = " ve "
    elif language == LANGUAGE_GERMAN:
        conjunction = " und "
    else:
        conjunction = " and "
    return ", ".join(names[:-1]) + conjunction + names[-1]


def _layer_phrase(recommendation: dict[str, Any], language: str = LANGUAGE_ENGLISH) -> str:
    """Join every recommended garment, including accessories, in ``language``."""
    names = [
        _localized_name(item_id, label, language)
        for item_id, label in _outfit_items(recommendation)
    ]
    if not names:
        return "the recommended layers"
    return _join_names(names, language)


def _sky_phrase(language: str, rain: float, wind: float) -> str:
    """Describe the sky with the same rain and wind thresholds as the cards."""
    rainy = rain >= RAIN_UMBRELLA_MIN_PROBABILITY_PERCENT
    windy = wind >= WIND_SHELL_MIN_MPS
    if language == LANGUAGE_TURKISH:
        if rainy and windy:
            return "hafif yağmurlu ve rüzgarlı"
        if rainy:
            return "hafif yağmurlu"
        if windy:
            return "rüzgarlı"
        return "açık"
    if language == LANGUAGE_GERMAN:
        if rainy and windy:
            return "leichtem Regen und böigem Wind"
        if rainy:
            return "leichtem Regen"
        if windy:
            return "böigem Wind"
        return "klarem Himmel"
    if rainy and windy:
        return "light rain and gusty winds"
    if rainy:
        return "light rain"
    if windy:
        return "gusty winds"
    return "clear skies"


def _format_degrees(value: float) -> str:
    """Render a temperature without a trailing decimal when it is whole."""
    rounded = round(float(value), 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _dual_temperature_clause(language: str, air: float, effective: float) -> str:
    """Return the air and feels-like temperatures in one labeled clause."""
    air_text = _format_degrees(air)
    feels_text = _format_degrees(effective)
    if language == LANGUAGE_TURKISH:
        return f"Hava sıcaklığı {air_text}°C, hissedilen ise {feels_text}°C."
    if language == LANGUAGE_GERMAN:
        return f"Die Lufttemperatur beträgt {air_text}°C, gefühlt sind es {feels_text}°C."
    return f"The air temperature is {air_text}°C, feeling like {feels_text}°C."


def deterministic_answer(
    question: str,
    city_name: str,
    recommendation: dict[str, Any],
    first_name: str | None = None,
    language: str | None = None,
) -> str:
    """Build two sentences from the same outfit the cards show.

    Sentence one greets the wearer with the city and sky. Sentence two
    lists every layer and accessory. The language follows ``question``,
    not the city name, unless the caller already chose one.
    """
    language = normalize_language(language) if language else detect_reply_language(question, city_name)
    weather = recommendation.get("meteorology")
    meteorology = weather if isinstance(weather, dict) else {}
    air = float(meteorology.get("air_temperature", 0.0))
    effective = float(
        recommendation.get(
            "effective_temperature_celsius",
            meteorology.get("apparent_temperature", air),
        )
    )
    rain = float(meteorology.get("rain_probability", 0.0))
    wind = float(meteorology.get("wind_speed", 0.0))
    sky = _sky_phrase(language, rain, wind)
    outfit = _layer_phrase(recommendation, language)
    temperatures = _dual_temperature_clause(language, air, effective)
    name = first_name.strip() if isinstance(first_name, str) else ""
    spoken_temperatures = temperatures.rstrip(".")
    if language == LANGUAGE_TURKISH:
        greeting = f"Merhaba {name}. " if name else "Merhaba. "
        return f"{greeting}{city_name} için {spoken_temperatures} ve {sky}. {outfit} giy."
    if language == LANGUAGE_GERMAN:
        greeting = f"Hallo {name}. " if name else "Hallo. "
        return f"{greeting}In {city_name}: {spoken_temperatures} bei {sky}. Trag {outfit}."
    greeting = f"Hello {name}. " if name else "Hello. "
    return f"{greeting}In {city_name}, {spoken_temperatures} with {sky}. Wear {outfit}."


def _context_message(
    question: str,
    city_name: str,
    recommendation: dict[str, Any],
    first_name: str | None,
    gender: str | None,
    personal_offset: float,
    language: str | None = None,
) -> str:
    """Describe only the facts the model is allowed to use."""
    weather = recommendation.get("meteorology")
    meteorology = weather if isinstance(weather, dict) else {}
    language = normalize_language(language) if language else detect_reply_language(question, city_name)
    effective = recommendation.get(
        "effective_temperature_celsius",
        meteorology.get("apparent_temperature"),
    )
    air = float(meteorology.get("air_temperature", 0.0))
    if not isinstance(effective, (int, float)):
        effective = meteorology.get("apparent_temperature", air)
    effective_value = float(effective)
    rain = float(meteorology.get("rain_probability", 0.0))
    wind = float(meteorology.get("wind_speed", 0.0))
    lines = [
        f"Required reply language: {_LANGUAGE_NAMES[language]}",
        "Place names do not choose the reply language.",
        "When stating the temperature, ALWAYS mention both the air temperature "
        f"({_format_degrees(air)}°C) and the effective feels-like temperature "
        f"({_format_degrees(effective_value)}°C) together. Never quote only one number.",
        f"Temperature clause: {_dual_temperature_clause(language, air, effective_value)}",
        f"City: {city_name}",
        f"Air temperature C: {_format_degrees(air)}",
        f"Effective temperature C: {_format_degrees(effective_value)}",
        f"Sky: {_sky_phrase(LANGUAGE_ENGLISH, rain, wind)}",
        f"Wind m/s: {wind}",
        f"Rain probability percent: {rain}",
        f"UV index: {meteorology.get('uv_index')}",
        f"Personal offset C: {personal_offset:+.1f}",
    ]
    for key, title in (
        ("base_layer", "Base layer"),
        ("mid_layer", "Mid layer"),
        ("outer_layer", "Outer layer"),
    ):
        fields = _garment_fields(recommendation.get(key))
        lines.append(f"{title}: {fields[1] if fields is not None else 'none'}")
    accessories = recommendation.get("accessories")
    if isinstance(accessories, list) and accessories:
        for item in accessories:
            fields = _garment_fields(item)
            if fields is not None:
                lines.append(f"Accessory: {fields[1]}")
    else:
        lines.append("Accessories: none")
    if first_name:
        lines.append(f"Wearer name: {first_name}")
    if gender:
        lines.append(f"Wearer gender: {gender}")
    stored_periods = recommendation.get("diurnal")
    if isinstance(stored_periods, list):
        lines.extend(diurnal_context_lines(stored_periods))
    lines.append(f"Question: {sanitize_prompt_text(question)}")
    return "\n".join(lines)


class VoiceChatService:
    """Build a short spoken answer from weather, clothing, and an optional profile."""

    def __init__(
        self,
        recommendation_service: RecommendationService,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Store the recommendation pipeline and an optional HTTP client.

        Args:
            recommendation_service: Weather and clothing source. Its weather
                cache is reused.
            settings: Cloudflare credentials. Loaded when omitted.
            http_client: Client used for Workers AI. A temporary client is
                opened when this is omitted.
        """
        self._recommendations = recommendation_service
        self._settings = settings if settings is not None else get_settings()
        self._client = http_client

    async def answer(
        self,
        *,
        question: str,
        latitude: float,
        longitude: float,
        city_name: str,
        user_id: UUID | None,
        db: AsyncSession | None,
    ) -> dict[str, str]:
        """Return reply text, language, and base64 MP3 audio.

        Args:
            question: The wearer's spoken question.
            latitude: Degrees north.
            longitude: Degrees east.
            city_name: Place name shown to the wearer.
            user_id: Authenticated wearer, or None for a guest.
            db: Open session used to read the profile. Guests pass None.

        Returns:
            ``answer_text``, ``language``, and ``audio_base64``. Audio is an
            empty string when speech synthesis cannot run.
        """
        first_name, gender, personal_offset, age = await self._profile(user_id, db)
        recommendation = await self._recommendations.get_recommendation(
            latitude=latitude,
            longitude=longitude,
            age=age,
            personal_offset=personal_offset,
            city_name=city_name,
            first_name=first_name,
            user_id=user_id,
            db=db,
        )
        context = _context_message(
            question,
            city_name,
            recommendation,
            first_name,
            gender,
            personal_offset,
        )
        language = detect_reply_language(question, city_name)
        model_text = await self._ask_model(context)
        if model_text is not None and _reply_matches_cards(
            model_text,
            question,
            city_name,
            recommendation,
        ):
            answer_text = limit_sentences(model_text)
        else:
            answer_text = deterministic_answer(
                question,
                city_name,
                recommendation,
                first_name=first_name,
            )
        audio_base64 = await self._speak(answer_text, language)
        return {
            "answer_text": answer_text,
            "language": language,
            "audio_base64": audio_base64,
        }

    async def answer_in_language(
        self,
        *,
        question: str,
        latitude: float,
        longitude: float,
        city_name: str,
        language: str,
        user_id: UUID | None,
        db: AsyncSession | None,
    ) -> dict[str, str]:
        """Answer in the requested language and speak that reply.

        Hourly morning, afternoon, and evening temperatures stay in the
        model context. The reply uses only the garments already chosen.
        """
        selected = normalize_language(language)
        first_name, gender, personal_offset, age = await self._profile(user_id, db)
        recommendation = await self._recommendations.get_recommendation(
            latitude=latitude,
            longitude=longitude,
            age=age,
            personal_offset=personal_offset,
            city_name=city_name,
            first_name=first_name,
            language=selected,
            user_id=user_id,
            db=db,
        )
        context = _context_message(
            question,
            city_name,
            recommendation,
            first_name,
            gender,
            personal_offset,
            language=selected,
        )
        model_text = await self._ask_model(context)
        if model_text is not None:
            answer_text = limit_sentences(model_text)
        else:
            answer_text = deterministic_answer(
                question,
                city_name,
                recommendation,
                first_name=first_name,
                language=selected,
            )
        audio_base64 = await self._speak(answer_text, selected)
        return {
            "answer_text": answer_text,
            "language": selected,
            "audio_base64": audio_base64,
        }

    async def _profile(
        self,
        user_id: UUID | None,
        db: AsyncSession | None,
    ) -> tuple[str | None, str | None, float, int]:
        """Return name, gender, thermal offset, and age in whole years."""
        if user_id is None or db is None:
            return None, None, 0.0, 30
        user = await db.get(User, user_id)
        if user is None:
            return None, None, 0.0, 30
        offset = await calculate_user_thermal_offset(user_id, db)
        age = await wearer_age_years(user_id, db)
        return user.first_name, user.gender, offset, age

    async def _ask_model(self, context: str) -> str | None:
        """Ask Llama for a reply, or return None so the caller can fall back."""
        if not cloudflare_credentials_configured(self._settings):
            logger.info("Cloudflare chat credentials are not configured. Using weather rules.")
            return None
        account_id = quote(self._settings.CLOUDFLARE_ACCOUNT_ID.strip(), safe="")
        token = self._settings.CLOUDFLARE_API_TOKEN.strip()
        url = LLAMA_RUN_URL.format(account_id=account_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "messages": [
                {"role": "system", "content": NIVA_CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": strip_prompt_delimiters(context)},
            ]
        }
        try:
            response = await self._post(url, headers, body)
            response.raise_for_status()
            payload = response.json()
        except (httpx.TimeoutException, httpx.HTTPError, ValueError):
            logger.warning("Cloudflare chat could not answer. Using weather rules.")
            return None
        if not isinstance(payload, dict) or payload.get("success") is False:
            logger.warning("Cloudflare chat reported an unsuccessful result. Using weather rules.")
            return None
        result = payload.get("result")
        if not isinstance(result, dict):
            return None
        reply = result.get("response")
        if not isinstance(reply, str) or reply.strip() == "":
            return None
        return limit_sentences(reply.strip())

    async def _post(
        self,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> httpx.Response:
        """POST one Workers AI chat request."""
        if self._client is not None:
            return await self._client.post(
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

    async def _speak(self, answer_text: str, language: str) -> str:
        """Return base64 MP3 bytes, or an empty string when synthesis fails."""
        try:
            audio = await generate_speech_audio(answer_text, voice=voice_for_language(language))
        except (VoiceUnavailableError, ValueError):
            logger.warning("Neural voice could not speak the answer.")
            return ""
        if audio == b"":
            return ""
        return base64.b64encode(audio).decode("ascii")

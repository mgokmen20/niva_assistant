"""Ask Cloudflare for one outfit, then for the daily briefing.

The thermal engine and the wardrobe filter decide which names are legal.
The stylist only marks those names true or false. The summary prompt
turns the chosen names and the rest of the day into a spoken briefing.
"""

import json
import logging
import re
from typing import Any, Final

import httpx

from ..core.config import Settings
from ..core.constants import PREFERRED_LANGUAGE_DE, PREFERRED_LANGUAGE_EN, PREFERRED_LANGUAGE_TR
from .llm_service import request_model_reply
from .tts_service import normalize_language
from .wardrobe_outfit import HybridPool

logger = logging.getLogger(__name__)

STYLIST_SYSTEM_PROMPT: Final[str] = (
    "You are a fashion stylist. The weather is {effective_temp}°C. "
    "Select exactly one top, one bottom, and one outerwear (if needed for the cold) "
    "from the provided list that match well in color and style. "
    "Also, select any relevant environmental accessories (like umbrella, sunglasses, or sunscreen) "
    "if they appear in the list. "
    "You MUST return ONLY a valid JSON object where keys are the exact item names "
    "and values are boolean true or false. No markdown, no conversational text."
)
_JSON_FENCE: Final[re.Pattern[str]] = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
SUMMARY_NLG_PROMPT: Final[str] = (
    "You are Niva, a premium digital wardrobe assistant. "
    "You do not choose clothes. You only speak the outfit that was already selected.\n"
    "Write a strictly concise daily briefing in {language}.\n"
    "DO NOT invent context like 'indoor activities'. "
    "DO NOT explain why the clothes were chosen. "
    "DO NOT write long paragraphs. "
    "DO NOT add conversational filler or closing remarks.\n"
    "\n"
    "Data:\n"
    "- User Name: {user_name}\n"
    "- Location: {location}\n"
    "- Weather Progression: {weather_progression}\n"
    "- Selected Outfit: {selected_items}\n"
    "\n"
    "**CRITICAL RULES & FORMAT:**\n"
    "Your response must follow this exact structure in a fluid but brief manner:\n"
    "1. **Greeting & Location:** Greet the user by name and mention the location. "
    "ALWAYS use time-neutral greetings (e.g., 'Hello {user_name}', 'Hi {user_name}') "
    "unless the exact current time is explicitly passed to you. Do not guess the time of day. "
    "If {language} is German/DE, use 'Grüezi {user_name}'.\n"
    "2. **Weather Summary:** State the current temperature, the peak temperature later, "
    "and any major conditions (like rain) in exactly 1 or 2 short sentences.\n"
    "3. **Outfit Recommendation:** Simply present the outfit using a direct phrase like "
    "'Bugün için önerilen kıyafetler:' (TR) / 'Recommended outfit:' (EN) / "
    "'Die heutige Kleidungsempfehlung:' (DE), followed by a natural listing of the {selected_items}.\n"
    "\n"
    "**Translation Rules:**\n"
    "- Accurately translate the {selected_items}.\n"
    "- When translating {selected_items} to the target {language}, you must strictly use ONLY "
    "that language. If {language} is English, output 'Pants' or 'Jeans' (NOT 'Kot Pantolon'), "
    "and 'Light Jacket' (NOT 'Light Jacke'). Do not mix vocabulary from other languages.\n"
    "- 'Hose' is Pants/Trousers (Pantolon).\n"
    "- 'Sweater' is Pullover (Kazak).\n"
    "\n"
    "CRITICAL ITEM RULE: You are strictly forbidden from changing, substituting, "
    "or adding any items to the {selected_items} list.\n"
    "- You must output the EXACT items provided. Treat the {selected_items} list as locked, "
    "immutable data.\n"
    "- Do NOT guess or swap accessories.\n"
    "- Translation constraints: If the input contains 'Umbrella', you MUST output 'Şemsiye' "
    "in Turkish and 'Regenschirm' in German. NEVER translate 'Umbrella' to 'Gözlük' (Glasses). "
    "If the input contains 'Sunglasses' or 'Glasses', only then use 'Güneş Gözlüğü' / 'Gözlük' (TR) "
    "or 'Sonnenbrille' (DE).\n"
    "\n"
    "**Example Output (English):**\n"
    "'Hello [Name]. Today in [Location], the temperature starts at 10°C, "
    "reaching 12°C in the afternoon, with rain expected at 13:00. "
    "The recommended outfit for today is: [Item 1], [Item 2], and [Item 3].'\n"
    "\n"
    "Do not deviate from this concise structure."
)
_LANGUAGE_LABELS: Final[dict[str, str]] = {
    PREFERRED_LANGUAGE_EN: "English",
    PREFERRED_LANGUAGE_DE: "German/DE",
    PREFERRED_LANGUAGE_TR: "Turkish",
}
_MISSING_FACT: Final[str] = "unknown"


def summary_system_prompt(
    *,
    language: str,
    weather_progression: str,
    selected_items: str,
    user_name: str = "",
    location: str = "",
) -> str:
    """Fill the daily-briefing prompt with the wearer, place, weather, and clothes."""
    selected = normalize_language(language)
    label = _LANGUAGE_LABELS.get(selected, _LANGUAGE_LABELS[PREFERRED_LANGUAGE_EN])
    progression = weather_progression.strip() if weather_progression.strip() != "" else "Not provided."
    outfit = selected_items.strip() if selected_items.strip() != "" else "No clothing selected."
    name = user_name.strip() if user_name.strip() != "" else _MISSING_FACT
    place = location.strip() if location.strip() != "" else _MISSING_FACT
    return (
        SUMMARY_NLG_PROMPT.replace("{language}", label)
        .replace("{user_name}", name)
        .replace("{location}", place)
        .replace("{weather_progression}", progression)
        .replace("{selected_items}", outfit)
    )


def selected_outfit_text(recommendation: dict[str, Any]) -> str:
    """List the clothes that were actually chosen, with no empty slots."""
    stored = recommendation.get("wardrobe_selection")
    if isinstance(stored, list):
        names = [name.strip() for name in stored if isinstance(name, str) and name.strip() != ""]
        if names:
            return ", ".join(names)
    names: list[str] = []
    tops = recommendation.get("tops")
    if isinstance(tops, list) and tops:
        names.extend(_garment_name(item) for item in tops)
    else:
        names.append(_garment_name(recommendation.get("base_layer")))
        names.append(_garment_name(recommendation.get("mid_layer")))
    names.append(_garment_name(recommendation.get("bottom")))
    outer = recommendation.get("outerwear")
    if not isinstance(outer, dict):
        outer = recommendation.get("outer_layer")
    names.append(_garment_name(outer))
    accessories = recommendation.get("accessories")
    if isinstance(accessories, list):
        names.extend(_garment_name(item) for item in accessories)
    unique = [name for name in names if isinstance(name, str) and name != ""]
    ordered: list[str] = []
    for name in unique:
        if name not in ordered:
            ordered.append(name)
    return ", ".join(ordered) if ordered else "No clothing selected."


def weather_progression_text(
    recommendation: dict[str, Any],
    *,
    air_temperature_celsius: float,
    effective_temperature_celsius: float,
) -> str:
    """Use the remaining-day sentence, or the current temperatures."""
    stored = recommendation.get("day_progression")
    if isinstance(stored, str) and stored.strip() != "":
        return stored.strip()
    air = _format_temperature(air_temperature_celsius)
    feels = _format_temperature(effective_temperature_celsius)
    return f"Currently {air}°C, feels like {feels}°C."


def stylist_system_prompt(effective_temperature_celsius: float) -> str:
    """Fill the stylist prompt with the decision temperature."""
    return STYLIST_SYSTEM_PROMPT.format(effective_temp=_format_temperature(effective_temperature_celsius))


def parse_stylist_selection(text: str, allowed_names: set[str]) -> list[str] | None:
    """Return pool names marked true.

    None means the reply is not a JSON object of booleans. An empty list
    means the JSON parsed and every known item was false.
    """
    cleaned = _JSON_FENCE.sub("", text.strip()).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("Cloudflare stylist reply was not valid JSON.")
        return None
    if not isinstance(parsed, dict):
        return None
    accepted: list[str] = []
    saw_boolean = False
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            continue
        saw_boolean = True
        if value and key in allowed_names:
            accepted.append(key)
    if not saw_boolean:
        return None
    return accepted


async def select_outfit_items(
    pool: HybridPool,
    *,
    effective_temperature_celsius: float,
    settings: Settings | None,
    http_client: httpx.AsyncClient | None = None,
) -> list[str] | None:
    """Ask the text model which pool names to wear.

    None means the call failed or the reply could not be parsed. The
    caller then picks one top, one bottom, and one outer layer itself.
    """
    reply = await request_model_reply(
        system_prompt=stylist_system_prompt(effective_temperature_celsius),
        user_content=_pool_message(pool),
        settings=settings,
        http_client=http_client,
    )
    if reply is None:
        return None
    return parse_stylist_selection(reply, {item.name for item in pool.items})


def _pool_message(pool: HybridPool) -> str:
    """List eligible names and whether an outer layer is required."""
    lines = [
        "Use these exact item names as JSON keys.",
        f"Outerwear is needed: {'yes' if pool.outerwear_required else 'no'}.",
        "Items:",
    ]
    for item in pool.items:
        if item.detail != "":
            lines.append(f"- {item.name} ({item.role}; {item.detail})")
        else:
            lines.append(f"- {item.name} ({item.role})")
    return "\n".join(lines)


def _garment_name(item: object) -> str:
    """Return a garment label, skipping empty slots."""
    if not isinstance(item, dict):
        return ""
    label = item.get("label")
    if not isinstance(label, str):
        return ""
    text = label.strip()
    if text == "" or text.lower() == "none":
        return ""
    return text


def _format_temperature(value: float) -> str:
    """Render a Celsius value without a trailing .0."""
    rounded = round(float(value), 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"

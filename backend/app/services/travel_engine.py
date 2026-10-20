"""Pack a multi-day trip from the coldest, wettest, and brightest days.

The clothing engine still decides today's outfit. This module only looks
across a date span and asks Cloudflare for a two-sentence brief when the
Workers AI credentials are present.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from ..core.config import Settings
from ..core.constants import (
    CLOTHING_FREEZING_BELOW_C,
    CLOTHING_MILD_BELOW_C,
    PREFERRED_LANGUAGE_DE,
    PREFERRED_LANGUAGE_EN,
    PREFERRED_LANGUAGE_TR,
    TRAVEL_CLEAR_WEATHER_CODES,
    TRAVEL_FLEECE_BELOW_C,
    TRAVEL_MAX_DAYS,
    TRAVEL_SHELL_MIN_PERCENT,
    TRAVEL_SNOW_WEATHER_CODES,
    TRAVEL_UMBRELLA_MIN_PERCENT,
    UV_PROTECTION_MIN_INDEX,
    WMO_PRECIPITATION_CODE_MIN,
)
from .llm_service import _limit_sentences, _swiss_spelling, garment_display_name, request_outfit_summary
from .tts_service import normalize_language
from .weather_service import WeatherService

CATEGORY_BASE = "base"
CATEGORY_MID = "mid"
CATEGORY_OUTER = "outer"
CATEGORY_ACCESSORY = "accessory"

ITEM_BASE_SHIRT = "base_shirt"
ITEM_FLEECE = "fleece"
ITEM_LIGHT_JACKET = "light_jacket"
ITEM_WINTER_COAT = "winter_coat"
ITEM_WATERPROOF_SHELL = "waterproof_shell"
ITEM_UMBRELLA = "umbrella"
ITEM_SUNGLASSES = "sunglasses"

TRAVEL_SYSTEM_PROMPTS: dict[str, str] = {
    PREFERRED_LANGUAGE_TR: (
        "Sen Niva adında samimi ve pratik bir seyahat asistanısın. "
        "Kullanıcının valiz listesini doğal Türkçe ile tam 2 kısa cümlede özetle. "
        "Adet söyleme; yalnızca hangi parça türlerinin gerektiğini söyle. "
        "Yağmur veya kar olasılığı yüzde 20 ile 40 arasındaysa tarihi ve yüzdeyi açıkça söyle "
        "ve tedbiren kompakt bir şemsiye önersin. "
        "Yüzde 40'ın altında 'yağmur var' veya 'yağmur tespit edildi' deme; bunu bir ihtimal olarak anlat. "
        "Yüzde 40 veya üzeri, ya da hava kodu yağmur veya kar gösteriyorsa, yağmurluk ve şemsiyeyi birlikte söyle. "
        "Yüzde 20'nin altında yağmur ekipmanı önerme. "
        "Yalnızca Türkçe yaz. Parça adlarını mesajdaki gibi kullan. "
        "Alt çizgili kod veya YYYY-AA-GG tarihi yazma. Şehir adını yalnızca bir kez kullan."
    ),
    PREFERRED_LANGUAGE_DE: (
        "Du bist Niva, ein freundlicher Reisebegleiter. "
        "Fasse die Packliste auf Schweizer Hochdeutsch (ohne ß, stattdessen ss) "
        "in genau 2 kurzen Sätzen zusammen. "
        "Nenne keine Stückzahlen, nur die Kleidungsarten. "
        "Liegt die Regen- oder Schneewahrscheinlichkeit zwischen 20 und 40 Prozent, "
        "nenne Datum und Prozentsatz und schlage vorsorglich einen kompakten Regenschirm vor. "
        "Sage unter 40 Prozent nie, dass Regen erkannt wurde. Formuliere es als vorsichtige Möglichkeit. "
        "Ab 40 Prozent, oder wenn der Wettercode Regen oder Schnee zeigt, nenne Regenjacke und Regenschirm. "
        "Unter 20 Prozent erwähne keinen Regenschutz. "
        "Schreibe nur auf Schweizer Hochdeutsch. Verwende die Kleidernamen genau so, wie sie in der Nachricht stehen. "
        "Schreibe keine Codes mit Unterstrich und kein Datum als JJJJ-MM-TT. Nenne die Stadt nur einmal."
    ),
    PREFERRED_LANGUAGE_EN: (
        "You are Niva, a practical travel companion. "
        "Summarize this packing list in exactly 2 short sentences. "
        "Do not give piece counts. Name only the garment types that are needed. "
        "When rain or snow probability is from 20 percent up to 40 percent, "
        "name the date and the percentage and suggest a compact umbrella as a precaution. "
        "Never say rain was detected for a probability under 40 percent. Frame it as an advisory risk. "
        "At 40 percent or higher, or when the weather code shows rain or snow, "
        "mention both a waterproof shell and an umbrella. "
        "Below 20 percent, do not recommend rain gear. "
        "Write in English only. Use the garment names exactly as written in the message. "
        "Do not write underscored codes or an ISO date. Mention the city only once."
    ),
}

_PRECIP_NONE = "none"
_PRECIP_ADVISORY = "advisory"
_PRECIP_HIGH = "high"
_RECOMMENDED_TYPE_QUANTITY = 1

_MONTH_NAMES: dict[str, tuple[str, ...]] = {
    PREFERRED_LANGUAGE_EN: (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    PREFERRED_LANGUAGE_DE: (
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
    PREFERRED_LANGUAGE_TR: (
        "Ocak",
        "Şubat",
        "Mart",
        "Nisan",
        "Mayıs",
        "Haziran",
        "Temmuz",
        "Ağustos",
        "Eylül",
        "Ekim",
        "Kasım",
        "Aralık",
    ),
}


class TravelWindowError(ValueError):
    """The requested dates cannot be planned from the forecast window."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_WINDOW_DETAILS: dict[str, str] = {
    "end_before_start": "The end date must be on or after the start date.",
    "too_long": f"A trip can cover at most {TRAVEL_MAX_DAYS} days.",
    "starts_in_past": "The start date cannot be in the past.",
    "beyond_forecast": f"The end date is outside the {TRAVEL_MAX_DAYS}-day forecast.",
    "no_days": "No forecast days fall inside this trip.",
}


def travel_window_detail(code: str) -> str:
    """Return a public message for a travel window code."""
    return _WINDOW_DETAILS.get(code, "The trip dates cannot be planned.")


@dataclass(frozen=True)
class TripDay:
    """One local forecast day used by the packing rules."""

    date: str
    temperature_min_c: float
    temperature_max_c: float
    precipitation_probability: float
    weather_code: int
    uv_index: float | None = None
    wind_speed_mps: float = 0.0


@dataclass(frozen=True)
class PackingItem:
    """One checklist row. Quantity stays 1 because the wearer chooses how many."""

    item_id: str
    category: str
    quantity: int


@dataclass(frozen=True)
class TravelPlan:
    """Packing list plus the two-sentence brief for one destination."""

    city_name: str
    start_date: str
    end_date: str
    summary: str
    items: list[PackingItem]
    days: list[TripDay]


def validate_trip_window(start: date, end: date, today: date) -> None:
    """Reject a span that starts in the past or leaves the forecast horizon."""
    if end < start:
        raise TravelWindowError("end_before_start")
    if (end - start).days + 1 > TRAVEL_MAX_DAYS:
        raise TravelWindowError("too_long")
    if start < today:
        raise TravelWindowError("starts_in_past")
    if (end - today).days + 1 > TRAVEL_MAX_DAYS:
        raise TravelWindowError("beyond_forecast")


def select_trip_days(forecast_days: list[TripDay], start: date, end: date) -> list[TripDay]:
    """Keep forecast rows whose date falls inside the inclusive trip."""
    selected: list[TripDay] = []
    for day in forecast_days:
        try:
            current = date.fromisoformat(day.date)
        except ValueError:
            continue
        if start <= current <= end:
            selected.append(day)
    return selected


def plan_packing(days: list[TripDay]) -> list[PackingItem]:
    """Build the bag from extremes across the whole span.

    Each row is a garment type, not a counted stack. Fleece is included
    when any night is below 12 °C. A winter coat is included when any
    night is below 5 °C. A light jacket is included when a day is cool
    enough for a shell but still reaches 5 °C. Precipitation below 20
    percent adds nothing. From 20 percent up to 40 percent, and only when
    the weather code is dry, a compact umbrella is added. At 40 percent,
    or when the WMO code is drizzle, rain, or snow, both a waterproof
    shell and an umbrella are added. Sunglasses follow UV 3 or a clear sky.
    """
    if not days:
        raise TravelWindowError("no_days")
    items: list[PackingItem] = [
        PackingItem(ITEM_BASE_SHIRT, CATEGORY_BASE, _RECOMMENDED_TYPE_QUANTITY),
    ]
    if any(day.temperature_min_c < TRAVEL_FLEECE_BELOW_C for day in days):
        items.append(PackingItem(ITEM_FLEECE, CATEGORY_MID, _RECOMMENDED_TYPE_QUANTITY))
    if any(_needs_light_jacket(day) for day in days):
        items.append(PackingItem(ITEM_LIGHT_JACKET, CATEGORY_OUTER, _RECOMMENDED_TYPE_QUANTITY))
    if any(day.temperature_min_c < CLOTHING_FREEZING_BELOW_C for day in days):
        items.append(PackingItem(ITEM_WINTER_COAT, CATEGORY_OUTER, _RECOMMENDED_TYPE_QUANTITY))
    tiers = {_precipitation_tier(day) for day in days}
    if _PRECIP_HIGH in tiers:
        items.append(PackingItem(ITEM_WATERPROOF_SHELL, CATEGORY_OUTER, _RECOMMENDED_TYPE_QUANTITY))
        items.append(PackingItem(ITEM_UMBRELLA, CATEGORY_ACCESSORY, _RECOMMENDED_TYPE_QUANTITY))
    elif _PRECIP_ADVISORY in tiers:
        items.append(PackingItem(ITEM_UMBRELLA, CATEGORY_ACCESSORY, _RECOMMENDED_TYPE_QUANTITY))
    if any(_needs_sunglasses(day) for day in days):
        items.append(PackingItem(ITEM_SUNGLASSES, CATEGORY_ACCESSORY, _RECOMMENDED_TYPE_QUANTITY))
    return items


def _needs_light_jacket(day: TripDay) -> bool:
    """True when the day is below the mild band and still reaches 5 °C."""
    cool = day.temperature_min_c < CLOTHING_MILD_BELOW_C
    not_only_freezing = day.temperature_max_c >= CLOTHING_FREEZING_BELOW_C
    return cool and not_only_freezing


def _precipitation_tier(day: TripDay) -> str:
    """Classify one day as no gear, umbrella only, or shell plus umbrella."""
    code_is_wet = day.weather_code >= WMO_PRECIPITATION_CODE_MIN
    if day.precipitation_probability >= TRAVEL_SHELL_MIN_PERCENT or code_is_wet:
        return _PRECIP_HIGH
    if day.precipitation_probability >= TRAVEL_UMBRELLA_MIN_PERCENT:
        return _PRECIP_ADVISORY
    return _PRECIP_NONE


def _is_snow(day: TripDay) -> bool:
    """True when the WMO code is snow rather than rain."""
    return day.weather_code in TRAVEL_SNOW_WEATHER_CODES


def _needs_sunglasses(day: TripDay) -> bool:
    """True when UV reaches the adult trigger or the sky is clear."""
    if day.uv_index is not None and day.uv_index >= UV_PROTECTION_MIN_INDEX:
        return True
    return day.weather_code in TRAVEL_CLEAR_WEATHER_CODES


_CLOTHING_ORDER: tuple[str, ...] = (
    ITEM_BASE_SHIRT,
    ITEM_FLEECE,
    ITEM_LIGHT_JACKET,
    ITEM_WINTER_COAT,
    ITEM_SUNGLASSES,
)
_WEEKDAY_NAMES: dict[str, tuple[str, ...]] = {
    PREFERRED_LANGUAGE_EN: ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    PREFERRED_LANGUAGE_DE: ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    PREFERRED_LANGUAGE_TR: ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"),
}
_RAW_TOKEN = re.compile(r"\b[a-z]+_[a-z0-9_]*\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _join_phrases(phrases: list[str], language: str) -> str:
    """Join phrases with a comma and a final conjunction."""
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    conjunction = " ve " if language == PREFERRED_LANGUAGE_TR else " und " if language == PREFERRED_LANGUAGE_DE else " and "
    if len(phrases) == 2:
        return f"{phrases[0]}{conjunction}{phrases[1]}"
    return ", ".join(phrases[:-1]) + conjunction + phrases[-1]


def _lower_first(text: str) -> str:
    """Lowercase the first character so two clauses can share one sentence."""
    if text == "":
        return text
    return text[0].lower() + text[1:]


def _spoken_date(iso_date: str, language: str) -> str:
    """Format a forecast date with the weekday, never as an ISO stamp."""
    try:
        current = date.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    month = _MONTH_NAMES[language][current.month - 1]
    weekday = _WEEKDAY_NAMES[language][current.weekday()]
    if language == PREFERRED_LANGUAGE_DE:
        return f"{weekday}, {current.day}. {month}"
    if language == PREFERRED_LANGUAGE_TR:
        return f"{current.day} {month} {weekday}"
    return f"{weekday}, {current.day} {month}"


def _kind_word(day: TripDay, language: str) -> str:
    """Return rain or snow in the summary language."""
    snow = _is_snow(day)
    if language == PREFERRED_LANGUAGE_TR:
        return "kar" if snow else "yağmur"
    if language == PREFERRED_LANGUAGE_DE:
        return "Schnee" if snow else "Regen"
    return "snow" if snow else "rain"


def _chance_phrase(day: TripDay, language: str) -> str:
    """One day's precipitation chance, cautious when the code is wet below 40 percent."""
    spoken = _spoken_date(day.date, language)
    percent = round(day.precipitation_probability)
    kind = _kind_word(day, language)
    code_below_shell = (
        _precipitation_tier(day) == _PRECIP_HIGH and day.precipitation_probability < TRAVEL_SHELL_MIN_PERCENT
    )
    if language == PREFERRED_LANGUAGE_TR:
        if code_below_shell:
            return f"{spoken} günü tahminde {kind} var ve ihtimal %{percent}"
        return f"{spoken} günü %{percent} {kind} ihtimali"
    if language == PREFERRED_LANGUAGE_DE:
        if code_below_shell:
            return f"am {spoken} zeigt die Vorhersage {kind} bei {percent} Prozent"
        return f"am {spoken} liegt die {kind}wahrscheinlichkeit bei {percent} Prozent"
    if code_below_shell:
        return f"on {spoken}, the forecast includes {kind} and the chance is {percent} percent"
    return f"on {spoken}, the {kind} chance is {percent} percent"


def _advisory_body(language: str, days: list[TripDay]) -> str:
    """Percentage plus a compact-umbrella precaution, with no claim that rain is certain."""
    joined = _join_phrases([_chance_phrase(day, language) for day in days], language)
    umbrella = garment_display_name(ITEM_UMBRELLA, language)
    if language == PREFERRED_LANGUAGE_TR:
        return f"{joined[0].upper()}{joined[1:]} görünüyor; tedbiren yanınıza {umbrella} almayı düşünebilirsiniz"
    if language == PREFERRED_LANGUAGE_DE:
        return f"{joined[0].upper()}{joined[1:]}, deshalb kann {umbrella} sinnvoll sein"
    return f"{joined[0].upper()}{joined[1:]}, so consider {umbrella}"


def _high_body(language: str, days: list[TripDay]) -> str:
    """Shell and umbrella for a high chance or a wet weather code."""
    joined = _join_phrases([_chance_phrase(day, language) for day in days], language)
    shell = garment_display_name(ITEM_WATERPROOF_SHELL, language)
    umbrella = garment_display_name(ITEM_UMBRELLA, language)
    if language == PREFERRED_LANGUAGE_TR:
        return f"{joined[0].upper()}{joined[1:]}; {shell} ve {umbrella} alın"
    if language == PREFERRED_LANGUAGE_DE:
        return f"{joined[0].upper()}{joined[1:]}, deshalb nehmen Sie {shell} und {umbrella} mit"
    return f"{joined[0].upper()}{joined[1:]}, so bring {shell} and {umbrella}"


def _dry_sentence(language: str) -> str:
    """Say that rain gear stays home when every day is below the umbrella cut."""
    cut = int(TRAVEL_UMBRELLA_MIN_PERCENT)
    umbrella = garment_display_name(ITEM_UMBRELLA, language)
    if language == PREFERRED_LANGUAGE_TR:
        return f"Hiçbir gün yüzde {cut} yağmur veya kar ihtimaline ulaşmıyor ve {umbrella} gerekmez."
    if language == PREFERRED_LANGUAGE_DE:
        return f"Kein Tag erreicht {cut} Prozent Regen oder Schnee, und {umbrella} bleibt zu Hause."
    return f"No day reaches a {cut} percent chance of rain or snow, and {umbrella} is not needed."


def _clothing_labels(items: list[PackingItem], language: str) -> list[str]:
    """Spoken clothing names in packing order. Rain gear stays in the weather sentence."""
    packed = {item.item_id for item in items}
    return [garment_display_name(item_id, language) for item_id in _CLOTHING_ORDER if item_id in packed]


def fallback_travel_summary(city_name: str, language: str, items: list[PackingItem], days: list[TripDay]) -> str:
    """Two local sentences used when Workers AI is not available."""
    selected = normalize_language(language)
    text = f"{_garment_sentence(city_name, selected, items)} {_precip_sentence(selected, days)}"
    if selected == PREFERRED_LANGUAGE_DE:
        return _swiss_spelling(text)
    return text


def _garment_sentence(city_name: str, language: str, items: list[PackingItem]) -> str:
    """Name the clothing types, without counts or rain gear."""
    joined = _join_phrases(_clothing_labels(items, language), language)
    if language == PREFERRED_LANGUAGE_TR:
        return f"{city_name} için {joined} alın."
    if language == PREFERRED_LANGUAGE_DE:
        return f"Packen Sie {joined} für {city_name} ein."
    return f"Pack {joined} for {city_name}."


def _precip_sentence(language: str, days: list[TripDay]) -> str:
    """State rain or snow chances without calling a low probability certain."""
    advisory = [day for day in days if _precipitation_tier(day) == _PRECIP_ADVISORY]
    high = [day for day in days if _precipitation_tier(day) == _PRECIP_HIGH]
    if not advisory and not high:
        return _dry_sentence(language)
    if advisory and high:
        left = _advisory_body(language, advisory)
        right = _lower_first(_high_body(language, high))
        conjunction = " ve " if language == PREFERRED_LANGUAGE_TR else " und " if language == PREFERRED_LANGUAGE_DE else ", and "
        return f"{left}{conjunction}{right}."
    if advisory:
        return f"{_advisory_body(language, advisory)}."
    return f"{_high_body(language, high)}."


def _decision_context(city_name: str, days: list[TripDay], items: list[PackingItem], language: str) -> str:
    """Facts in ``language``, using spoken names and dates instead of raw ids."""
    selected = normalize_language(language)
    return f"{_garment_sentence(city_name, selected, items)} {_precip_sentence(selected, days)}"


async def compose_travel_summary(
    *,
    city_name: str,
    language: str,
    items: list[PackingItem],
    days: list[TripDay],
    settings: Settings | None,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """Ask Llama for two sentences, then fall back to the local brief."""
    selected = normalize_language(language)
    fallback = fallback_travel_summary(city_name, selected, items, days)
    reply = await request_outfit_summary(
        language=selected,
        context=_decision_context(city_name, days, items, selected),
        settings=settings,
        http_client=http_client,
        system_prompt=TRAVEL_SYSTEM_PROMPTS[selected],
    )
    if reply is None:
        return fallback
    cleaned = _swiss_spelling(reply) if selected == PREFERRED_LANGUAGE_DE else reply
    limited = _limit_sentences(cleaned)
    if not _travel_reply_ok(limited, selected) or _mentions_city_twice(limited, city_name):
        return fallback
    return limited


def _mentions_city_twice(text: str, city_name: str) -> bool:
    """True when the brief repeats the destination."""
    token = city_name.strip().casefold()
    if len(token) < 2:
        return False
    return text.casefold().count(token) > 1


def _travel_reply_ok(text: str, language: str) -> bool:
    """Accept a two-sentence brief that stays in the requested language."""
    if _RAW_TOKEN.search(text.casefold()) is not None or _ISO_DATE.search(text) is not None:
        return False
    words = set(text.casefold().split())
    turkish_marks = any(character in text for character in "ğĞşŞıİçÇöÖüÜ")
    if language == PREFERRED_LANGUAGE_TR:
        return turkish_marks or bool(words & {"için", "gün", "valiz", "günlere"})
    if language == PREFERRED_LANGUAGE_DE:
        if "ß" in text:
            return False
        return bool(words & {"und", "ist", "sind", "sie", "für", "fuer", "tag", "tage", "packen", "nehmen"})
    return bool(words & {"the", "and", "your", "pack", "bring", "for"}) and not turkish_marks


def _trip_day(row: dict[str, Any]) -> TripDay:
    """Map one parsed forecast row onto a trip day."""
    uv_value = row.get("uv_index")
    uv_index = float(uv_value) if isinstance(uv_value, (int, float)) and not isinstance(uv_value, bool) else None
    wind_value = row.get("wind_speed")
    wind_speed = float(wind_value) if isinstance(wind_value, (int, float)) and not isinstance(wind_value, bool) else 0.0
    return TripDay(
        date=str(row["date"]),
        temperature_min_c=float(row["temperature_min"]),
        temperature_max_c=float(row["temperature_max"]),
        precipitation_probability=float(row["precipitation_probability"]),
        weather_code=int(row["weather_code"]),
        uv_index=uv_index,
        wind_speed_mps=wind_speed,
    )


async def build_travel_plan(
    *,
    weather_service: WeatherService,
    latitude: float,
    longitude: float,
    city_name: str,
    start: date,
    end: date,
    language: str,
    today: date | None = None,
    settings: Settings | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> TravelPlan:
    """Fetch the destination forecast and pack the inclusive date span."""
    current_day = date.today() if today is None else today
    validate_trip_window(start, end, current_day)
    day_count = (end - current_day).days + 1
    rows = await weather_service.fetch_daily_forecast(
        latitude,
        longitude,
        day_count=day_count,
        include_uv=True,
    )
    forecast_days = [_trip_day(row) for row in rows]
    selected = select_trip_days(forecast_days, start, end)
    items = plan_packing(selected)
    summary = await compose_travel_summary(
        city_name=city_name,
        language=language,
        items=items,
        days=selected,
        settings=settings,
        http_client=http_client,
    )
    return TravelPlan(
        city_name=city_name,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        summary=summary,
        items=items,
        days=selected,
    )

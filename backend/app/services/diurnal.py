"""Daytime temperature swing and the removable layer it calls for.

The thermal engine still chooses the outfit. This module only describes
morning, afternoon, and evening when the day moves by at least the
named swing, so a wearer can add a layer they can take off later.
"""

from typing import Any, Final

from ..core.constants import DIURNAL_SWING_MIN_CELSIUS

_PERIOD_ORDER: Final[tuple[str, ...]] = ("morning", "afternoon", "evening")
_ZIP: Final[str] = "zip"
_WIND: Final[str] = "wind"
_CARDIGAN: Final[str] = "cardigan"


def temperature_swing(periods: list[dict[str, Any]]) -> float | None:
    """Return the afternoon-morning-evening range, or None when a period is missing."""
    temperatures = [_temperature(periods, name) for name in _PERIOD_ORDER]
    if any(value is None for value in temperatures):
        return None
    values = [value for value in temperatures if value is not None]
    return max(values) - min(values)


def adaptability_sentence(language: str, periods: list[dict[str, Any]]) -> str | None:
    """Return one localized day-shift sentence when the swing is large enough."""
    swing = temperature_swing(periods)
    if swing is None or swing < DIURNAL_SWING_MIN_CELSIUS:
        return None
    morning = _temperature(periods, "morning")
    afternoon = _temperature(periods, "afternoon")
    evening = _temperature(periods, "evening")
    if morning is None or afternoon is None or evening is None:
        return None
    piece = _removable_piece(min(morning, afternoon, evening), max(morning, afternoon, evening))
    return _sentence(language, piece, morning, afternoon, evening)


def diurnal_context_lines(periods: list[dict[str, Any]]) -> list[str]:
    """Return English facts for a model prompt, including the swing rule."""
    if not periods:
        return []
    lines = [
        "Hourly local temperatures: "
        + ", ".join(
            f"{item.get('period')} {_format_hour(item.get('temperature'))}C"
            for item in periods
            if isinstance(item, dict)
        )
    ]
    swing = temperature_swing(periods)
    if swing is not None and swing >= DIURNAL_SWING_MIN_CELSIUS:
        lines.append(
            f"The daytime swing is {swing:.1f}C, which is at least {DIURNAL_SWING_MIN_CELSIUS:.0f}C. "
            "Mention a removable full-zip fleece, cardigan, or packable windbreaker."
        )
    return lines


def _removable_piece(low: float, high: float) -> str:
    """Pick the removable piece that matches the cold and warm ends of the day."""
    if low < 13.0:
        return _ZIP
    if high >= 19.0:
        return _WIND
    return _CARDIGAN


def _sentence(language: str, piece: str, morning: float, afternoon: float, evening: float) -> str:
    """Return the day-shift sentence in English, Swiss German, or Turkish."""
    morning_c = round(morning)
    afternoon_c = round(afternoon)
    evening_c = round(evening)
    code = language if language in {"de", "tr"} else "en"
    if code == "tr":
        if piece == _ZIP:
            return (
                f"Sabah {morning_c}°C ile serin başlayıp öğlen {afternoon_c}°C'ye çıkacağı için "
                "çıkarılabilir bir fermuarlı polar tercih et."
            )
        if piece == _WIND:
            return (
                f"Sabah {morning_c}°C, öğlen {afternoon_c}°C olacağı için katlanabilir bir rüzgarlık tercih et."
            )
        return (
            f"Sabah {morning_c}°C ile akşam {evening_c}°C arasında değişeceği için "
            "çıkarılabilir bir hırka tercih et."
        )
    if code == "de":
        if piece == _ZIP:
            return (
                f"Der Morgen startet bei {morning_c}°C und der Nachmittag erreicht {afternoon_c}°C, "
                "darum passt ein abnehmbarer Fleece mit Reissverschluss."
            )
        if piece == _WIND:
            return (
                f"Der Morgen liegt bei {morning_c}°C und der Nachmittag bei {afternoon_c}°C, "
                "darum passt eine packbare Windjacke."
            )
        return (
            f"Der Tag schwankt zwischen {morning_c}°C und {afternoon_c}°C, "
            "darum passt eine abnehmbare Strickjacke."
        )
    if piece == _ZIP:
        return (
            f"The morning starts at {morning_c}°C and the afternoon reaches {afternoon_c}°C, "
            "so choose a removable full-zip fleece."
        )
    if piece == _WIND:
        return (
            f"The morning is {morning_c}°C and the afternoon is {afternoon_c}°C, "
            "so pack a packable windbreaker."
        )
    return (
        f"The day swings from {morning_c}°C to {evening_c}°C, so choose a removable cardigan."
    )


def _temperature(periods: list[dict[str, Any]], name: str) -> float | None:
    """Return one named period temperature."""
    for item in periods:
        if item.get("period") != name:
            continue
        value = item.get("temperature")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)
    return None


def _format_hour(value: object) -> str:
    """Format a period temperature for the model context."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "unknown"
    return f"{float(value):.1f}"

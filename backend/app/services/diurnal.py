"""Local morning, afternoon, and evening temperatures.

These facts describe the day. They do not add clothing.
"""

from typing import Any, Final

_PERIOD_ORDER: Final[tuple[str, ...]] = ("morning", "afternoon", "evening")


def temperature_swing(periods: list[dict[str, Any]]) -> float | None:
    """Return the afternoon-morning-evening range, or None when a period is missing."""
    temperatures = [_temperature(periods, name) for name in _PERIOD_ORDER]
    if any(value is None for value in temperatures):
        return None
    values = [value for value in temperatures if value is not None]
    return max(values) - min(values)


def diurnal_context_lines(periods: list[dict[str, Any]]) -> list[str]:
    """Return the local morning, afternoon, and evening temperatures."""
    if not periods:
        return []
    listed = ", ".join(
        f"{item.get('period')} {_format_hour(item.get('temperature'))}C"
        for item in periods
        if isinstance(item, dict)
    )
    if listed.strip() == "":
        return []
    return [f"Hourly local temperatures: {listed}"]


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

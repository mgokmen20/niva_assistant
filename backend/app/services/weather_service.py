"""Async client for the Open-Meteo forecast API.

This service performs HTTP I/O and maps the provider payload onto the
domain :class:`~app.domain.thermal_engine.ThermalInput`. It does not choose
clothing and it does not import a web framework or a database library.
"""

import asyncio
import copy
import math
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, Final

import httpx

from ..core.constants import (
    DIURNAL_AFTERNOON_HOUR,
    DIURNAL_EVENING_HOUR,
    DIURNAL_MORNING_HOUR,
    FORECAST_DAY_COUNT,
    TRAVEL_MAX_DAYS,
)
from ..core.exceptions import WeatherAPIUnavailableError, WeatherServiceError
from ..domain.thermal_engine import ThermalInput

REQUEST_TIMEOUT_SECONDS: Final[float] = 5.0
DEFAULT_OPEN_METEO_FORECAST_URL: Final[str] = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_BASE_URL_ENV: Final[str] = "OPEN_METEO_BASE_URL"
FORECAST_PATH: Final[str] = "/v1/forecast"
# Open-Meteo documents km/h as the default unit for wind_speed_10m.
# ThermalInput.wind_speed is metres per second.
KILOMETRES_PER_HOUR_PER_METRE_PER_SECOND: Final[float] = 3.6
CURRENT_VARIABLES: Final[str] = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,"
    "wind_speed_10m,precipitation_probability,uv_index,weather_code"
)
DAILY_FORECAST_VARIABLES: Final[str] = (
    "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
)
DAILY_TRAVEL_VARIABLES: Final[str] = (
    f"{DAILY_FORECAST_VARIABLES},uv_index_max,wind_speed_10m_max"
)
HOURLY_DIURNAL_VARIABLES: Final[str] = "temperature_2m,weather_code"
_DIURNAL_TARGETS: Final[tuple[tuple[str, int], ...]] = (
    ("morning", DIURNAL_MORNING_HOUR),
    ("afternoon", DIURNAL_AFTERNOON_HOUR),
    ("evening", DIURNAL_EVENING_HOUR),
)
TIMEZONE_AUTO: Final[str] = "auto"
LATITUDE_MIN_DEGREES: Final[float] = -90.0
LATITUDE_MAX_DEGREES: Final[float] = 90.0
LONGITUDE_MIN_DEGREES: Final[float] = -180.0
LONGITUDE_MAX_DEGREES: Final[float] = 180.0
# Forecasts for the same neighbourhood are reused for ten minutes.
WEATHER_CACHE_TTL_SECONDS: Final[float] = 600.0
WEATHER_CACHE_COORDINATE_DECIMALS: Final[int] = 2
# Extra attempts after the first timeout or connection failure.
WEATHER_RETRY_COUNT: Final[int] = 2
# Delays before retry 1 and retry 2 are 0.25s and 0.5s.
WEATHER_RETRY_BASE_DELAY_SECONDS: Final[float] = 0.25

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


def _resolve_forecast_url(forecast_url: str | None) -> str:
    """Return the forecast URL, honouring ``OPEN_METEO_BASE_URL`` when set.

    The environment variable is the API origin (for example
    ``https://api.open-meteo.com``). The forecast path is appended when the
    value does not already end with it. An explicit ``forecast_url`` wins
    so tests can point at a fake host.
    """
    if forecast_url is not None:
        return forecast_url
    configured = os.environ.get(OPEN_METEO_BASE_URL_ENV, "").strip()
    if not configured:
        return DEFAULT_OPEN_METEO_FORECAST_URL
    base = configured.rstrip("/")
    if base.endswith(FORECAST_PATH):
        return base
    return f"{base}{FORECAST_PATH}"


def _require_coordinate(name: str, value: float, minimum: float, maximum: float) -> float:
    """Return ``value`` when it is a finite coordinate inside ``minimum`` and ``maximum``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number of degrees.")
    number = float(value)
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum} degrees.")
    return number


def _cache_key(latitude: float, longitude: float) -> tuple[float, float]:
    """Round a coordinate pair so nearby readings share one cache entry."""
    places = WEATHER_CACHE_COORDINATE_DECIMALS
    return (round(latitude, places), round(longitude, places))


class WeatherCache:
    """Process-local forecast cache with a fixed time to live.

    Keys are coordinates rounded to two decimal places (about 1 km).
    A hit returns a deep copy so callers cannot change the stored payload.
    """

    def __init__(
        self,
        ttl_seconds: float = WEATHER_CACHE_TTL_SECONDS,
        clock: Clock | None = None,
    ) -> None:
        """Store the lifetime and the clock used to expire entries.

        Args:
            ttl_seconds: How long a stored forecast stays valid.
            clock: Seconds source. Defaults to ``time.monotonic``.
        """
        self._ttl_seconds = ttl_seconds
        self._clock = clock if clock is not None else time.monotonic
        self._entries: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}

    def get(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        """Return a copy of a fresh forecast, or ``None`` when missing or expired."""
        key = _cache_key(latitude, longitude)
        stored = self._entries.get(key)
        if stored is None:
            return None
        stored_at, payload = stored
        if self._clock() - stored_at >= self._ttl_seconds:
            del self._entries[key]
            return None
        return copy.deepcopy(payload)

    def put(self, latitude: float, longitude: float, payload: dict[str, Any]) -> None:
        """Store a copy of ``payload`` under the rounded coordinate key."""
        key = _cache_key(latitude, longitude)
        self._entries[key] = (self._clock(), copy.deepcopy(payload))


# One cache for every WeatherService created by the API process.
SHARED_WEATHER_CACHE = WeatherCache()


class DailyForecastCache:
    """Cache for daily rows, kept apart from the current-weather payload.

    A daily response has no ``current`` block. Storing it under the same
    key as the live observation would make the next current read fail.
    """

    def __init__(
        self,
        ttl_seconds: float = WEATHER_CACHE_TTL_SECONDS,
        clock: Clock | None = None,
    ) -> None:
        """Store the lifetime and the clock used to expire entries."""
        self._ttl_seconds = ttl_seconds
        self._clock = clock if clock is not None else time.monotonic
        self._entries: dict[tuple[float, float, int, bool], tuple[float, list[dict[str, Any]]]] = {}

    def get(
        self,
        latitude: float,
        longitude: float,
        day_count: int,
        include_uv: bool,
    ) -> list[dict[str, Any]] | None:
        """Return a copy of fresh daily rows, or ``None`` when missing."""
        key = (*_cache_key(latitude, longitude), day_count, include_uv)
        stored = self._entries.get(key)
        if stored is None:
            return None
        stored_at, rows = stored
        if self._clock() - stored_at >= self._ttl_seconds:
            del self._entries[key]
            return None
        return copy.deepcopy(rows)

    def put(
        self,
        latitude: float,
        longitude: float,
        day_count: int,
        include_uv: bool,
        rows: list[dict[str, Any]],
    ) -> None:
        """Store a copy of the parsed daily rows."""
        key = (*_cache_key(latitude, longitude), day_count, include_uv)
        self._entries[key] = (self._clock(), copy.deepcopy(rows))


SHARED_DAILY_CACHE = DailyForecastCache()


class DiurnalCache:
    """Process-local cache for the three daytime hours. It does not store current weather."""

    def __init__(
        self,
        ttl_seconds: float = WEATHER_CACHE_TTL_SECONDS,
        clock: Clock | None = None,
    ) -> None:
        """Store the lifetime and the clock used to expire entries."""
        self._ttl_seconds = ttl_seconds
        self._clock = clock if clock is not None else time.monotonic
        self._entries: dict[tuple[float, float], tuple[float, list[dict[str, Any]]]] = {}

    def get(self, latitude: float, longitude: float) -> list[dict[str, Any]] | None:
        """Return a copy of a fresh daytime row, or None when it is missing."""
        stored = self._entries.get(_cache_key(latitude, longitude))
        if stored is None:
            return None
        stored_at, rows = stored
        if self._clock() - stored_at >= self._ttl_seconds:
            return None
        return copy.deepcopy(rows)

    def put(self, latitude: float, longitude: float, rows: list[dict[str, Any]]) -> None:
        """Store a copy of the morning, afternoon, and evening rows."""
        self._entries[_cache_key(latitude, longitude)] = (self._clock(), copy.deepcopy(rows))


SHARED_DIURNAL_CACHE = DiurnalCache()


def _optional_weather_code(current: dict[str, Any]) -> int:
    """Return the WMO code when the provider sent one, otherwise zero."""
    value = current.get("weather_code", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    code = int(value)
    if code < 0:
        return 0
    return code


def _required_float(current: dict[str, Any], field_name: str) -> float:
    """Return one numeric ``current`` field or raise when it cannot be used."""
    if field_name not in current:
        raise WeatherServiceError(f"Open-Meteo current block is missing {field_name}.")
    value = current[field_name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherServiceError(f"Open-Meteo field {field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise WeatherServiceError(f"Open-Meteo field {field_name} must be finite.")
    return number


def _finite_number(value: object, field_name: str) -> float:
    """Return a finite float from one daily cell."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherServiceError(f"Open-Meteo daily field {field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise WeatherServiceError(f"Open-Meteo daily field {field_name} must be finite.")
    return number


def _daily_rows(payload: dict[str, Any], include_uv: bool) -> list[dict[str, Any]]:
    """Turn the Open-Meteo ``daily`` object into one dict per date."""
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise WeatherServiceError("Open-Meteo payload is missing the daily block.")
    dates = daily.get("time")
    highs = daily.get("temperature_2m_max")
    lows = daily.get("temperature_2m_min")
    rain = daily.get("precipitation_probability_max")
    codes = daily.get("weather_code")
    columns: list[object] = [dates, highs, lows, rain, codes]
    uv_values = daily.get("uv_index_max") if include_uv else None
    wind_values = daily.get("wind_speed_10m_max") if include_uv else None
    if include_uv:
        columns.append(uv_values)
        columns.append(wind_values)
    if any(not isinstance(column, list) for column in columns):
        raise WeatherServiceError("Open-Meteo daily forecast is incomplete.")
    assert isinstance(dates, list)
    assert isinstance(highs, list)
    assert isinstance(lows, list)
    assert isinstance(rain, list)
    assert isinstance(codes, list)
    length = len(dates)
    if any(len(column) != length for column in columns if isinstance(column, list)):
        raise WeatherServiceError("Open-Meteo daily forecast arrays differ in length.")
    rows: list[dict[str, Any]] = []
    for index, day in enumerate(dates):
        if not isinstance(day, str) or day.strip() == "":
            raise WeatherServiceError("Open-Meteo daily forecast is missing a date.")
        row: dict[str, Any] = {
            "date": day,
            "temperature_max": _finite_number(highs[index], "temperature_2m_max"),
            "temperature_min": _finite_number(lows[index], "temperature_2m_min"),
            "precipitation_probability": _finite_number(rain[index], "precipitation_probability_max"),
            "weather_code": int(_finite_number(codes[index], "weather_code")),
        }
        if include_uv:
            assert isinstance(uv_values, list)
            assert isinstance(wind_values, list)
            row["uv_index"] = _finite_number(uv_values[index], "uv_index_max")
            # Open-Meteo daily wind is kilometres per hour. The app speaks m/s.
            row["wind_speed"] = (
                _finite_number(wind_values[index], "wind_speed_10m_max")
                / KILOMETRES_PER_HOUR_PER_METRE_PER_SECOND
            )
        rows.append(row)
    return rows


class WeatherService:
    """Fetch current conditions from Open-Meteo and map them to the domain.

    Pass an existing :class:`httpx.AsyncClient` to reuse connections. When
    no client is supplied, each call opens and closes its own client.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        forecast_url: str | None = None,
        cache: WeatherCache | None = None,
        sleeper: Sleep | None = None,
        daily_cache: DailyForecastCache | None = None,
        diurnal_cache: DiurnalCache | None = None,
    ) -> None:
        """Store the HTTP client, forecast endpoint, and forecast cache.

        Args:
            client: Optional async client. The service does not close a
                client it did not create.
            forecast_url: Full forecast URL. When omitted, the URL is built
                from ``OPEN_METEO_BASE_URL`` or the public Open-Meteo host.
            cache: Forecast cache. When omitted, a private cache is used.
                The API passes :data:`SHARED_WEATHER_CACHE` so requests
                share one ten-minute store.
            sleeper: Awaitable delay used between retries. Tests can
                replace ``asyncio.sleep``.
        """
        self._client = client
        self._forecast_url = _resolve_forecast_url(forecast_url)
        self._cache = cache if cache is not None else WeatherCache()
        self._daily_cache = daily_cache if daily_cache is not None else DailyForecastCache()
        self._diurnal_cache = diurnal_cache if diurnal_cache is not None else DiurnalCache()
        self._sleep = sleeper if sleeper is not None else asyncio.sleep

    async def current_meteorology(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Return the public weather fields without a clothing decision.

        Wind is converted to metres per second. Apparent temperature is the
        Open-Meteo feels-like value, not the clothing engine's effective
        temperature.
        """
        raw_weather = await self.fetch_current_weather(latitude, longitude)
        current = raw_weather.get("current")
        if not isinstance(current, dict):
            raise WeatherServiceError("Open-Meteo payload is missing the current block.")
        wind_kmh = _required_float(current, "wind_speed_10m")
        try:
            diurnal = await self.fetch_diurnal_periods(latitude, longitude)
        except (WeatherAPIUnavailableError, WeatherServiceError):
            diurnal = []
        return {
            "air_temperature": _required_float(current, "temperature_2m"),
            "apparent_temperature": _required_float(current, "apparent_temperature"),
            "wind_speed": wind_kmh / KILOMETRES_PER_HOUR_PER_METRE_PER_SECOND,
            "rain_probability": _required_float(current, "precipitation_probability"),
            "uv_index": _required_float(current, "uv_index"),
            "diurnal": diurnal,
        }

    async def fetch_diurnal_periods(self, latitude: float, longitude: float) -> list[dict[str, Any]]:
        """Return local morning, afternoon, and evening temperatures.

        The request is cached on its own and does not replace the current
        observation. Missing hours are omitted rather than invented.
        """
        checked_latitude = _require_coordinate(
            "latitude",
            latitude,
            LATITUDE_MIN_DEGREES,
            LATITUDE_MAX_DEGREES,
        )
        checked_longitude = _require_coordinate(
            "longitude",
            longitude,
            LONGITUDE_MIN_DEGREES,
            LONGITUDE_MAX_DEGREES,
        )
        cached = self._diurnal_cache.get(checked_latitude, checked_longitude)
        if cached is not None:
            return cached
        params: dict[str, float | str] = {
            "latitude": checked_latitude,
            "longitude": checked_longitude,
            "hourly": HOURLY_DIURNAL_VARIABLES,
            "forecast_days": "2",
            "past_days": "1",
            "timezone": TIMEZONE_AUTO,
        }
        response = await self._request_with_retry(params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherServiceError("Open-Meteo returned a body that is not JSON.") from exc
        if not isinstance(payload, dict):
            raise WeatherServiceError("Open-Meteo returned a JSON value that is not an object.")
        rows = _diurnal_rows(payload)
        self._diurnal_cache.put(checked_latitude, checked_longitude, rows)
        return rows

    async def fetch_current_weather(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Return the raw Open-Meteo JSON object for one coordinate.

        The request asks for the current variables
        ``temperature_2m``, ``apparent_temperature``,
        ``relative_humidity_2m``, ``wind_speed_10m``,
        ``precipitation_probability``, and ``uv_index``, with
        ``timezone=auto``. The call budget is 5.0 seconds.

        A forecast cached for the same coordinates, rounded to two
        decimal places, is returned immediately and does not open a
        network call. The cache lifetime is 10 minutes.

        Timeouts and connection failures are retried twice with
        exponential backoff (0.25s, then 0.5s). When those retries are
        exhausted the service raises :class:`WeatherAPIUnavailableError`,
        which the HTTP layer maps to status 503. Other transport failures
        raise that same error without a retry. An HTTP error status or a
        body that is not a JSON object raises :class:`WeatherServiceError`.

        Args:
            latitude: Degrees north, from -90 to 90.
            longitude: Degrees east, from -180 to 180.

        Returns:
            The decoded Open-Meteo response object.
        """
        checked_latitude = _require_coordinate(
            "latitude",
            latitude,
            LATITUDE_MIN_DEGREES,
            LATITUDE_MAX_DEGREES,
        )
        checked_longitude = _require_coordinate(
            "longitude",
            longitude,
            LONGITUDE_MIN_DEGREES,
            LONGITUDE_MAX_DEGREES,
        )
        params: dict[str, float | str] = {
            "latitude": checked_latitude,
            "longitude": checked_longitude,
            "current": CURRENT_VARIABLES,
            "timezone": TIMEZONE_AUTO,
        }
        cached = self._cache.get(checked_latitude, checked_longitude)
        if cached is not None:
            return cached
        response = await self._request_with_retry(params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherServiceError("Open-Meteo returned a body that is not JSON.") from exc
        if not isinstance(payload, dict):
            raise WeatherServiceError("Open-Meteo returned a JSON value that is not an object.")
        self._cache.put(checked_latitude, checked_longitude, payload)
        return payload

    async def fetch_daily_forecast(
        self,
        latitude: float,
        longitude: float,
        day_count: int = FORECAST_DAY_COUNT,
        include_uv: bool = False,
    ) -> list[dict[str, Any]]:
        """Return one row per forecast day without touching the current cache.

        The public strip asks for seven days. A trip can ask for up to
        ``TRAVEL_MAX_DAYS`` and may include ``uv_index_max``.

        Raises:
            ValueError: ``day_count`` is outside 1 and ``TRAVEL_MAX_DAYS``.
            WeatherAPIUnavailableError: The provider could not be reached.
            WeatherServiceError: The daily block is missing or malformed.
        """
        if isinstance(day_count, bool) or not isinstance(day_count, int):
            raise ValueError("day_count must be a whole number of days.")
        if day_count < 1 or day_count > TRAVEL_MAX_DAYS:
            raise ValueError(f"day_count must be between 1 and {TRAVEL_MAX_DAYS}.")
        checked_latitude = _require_coordinate(
            "latitude",
            latitude,
            LATITUDE_MIN_DEGREES,
            LATITUDE_MAX_DEGREES,
        )
        checked_longitude = _require_coordinate(
            "longitude",
            longitude,
            LONGITUDE_MIN_DEGREES,
            LONGITUDE_MAX_DEGREES,
        )
        cached = self._daily_cache.get(checked_latitude, checked_longitude, day_count, include_uv)
        if cached is not None:
            return cached
        params: dict[str, float | str] = {
            "latitude": checked_latitude,
            "longitude": checked_longitude,
            "daily": DAILY_TRAVEL_VARIABLES if include_uv else DAILY_FORECAST_VARIABLES,
            "forecast_days": str(day_count),
            "timezone": TIMEZONE_AUTO,
        }
        response = await self._request_with_retry(params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise WeatherServiceError("Open-Meteo returned a body that is not JSON.") from exc
        if not isinstance(payload, dict):
            raise WeatherServiceError("Open-Meteo returned a JSON value that is not an object.")
        rows = _daily_rows(payload, include_uv=include_uv)
        self._daily_cache.put(checked_latitude, checked_longitude, day_count, include_uv, rows)
        return rows

    async def _request_with_retry(self, params: dict[str, float | str]) -> httpx.Response:
        """GET the forecast, retrying timeouts and connection errors twice.

        Raises:
            WeatherAPIUnavailableError: The provider timed out, refused
                the connection, or another transport error occurred.
            WeatherServiceError: The provider answered with an HTTP error.
        """
        attempt = 0
        while True:
            try:
                response = await self._send(params)
                response.raise_for_status()
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt >= WEATHER_RETRY_COUNT:
                    raise WeatherAPIUnavailableError(
                        "Open-Meteo did not respond after 2 retries."
                    ) from exc
                delay = WEATHER_RETRY_BASE_DELAY_SECONDS * (2**attempt)
                await self._sleep(delay)
                attempt += 1
                continue
            except httpx.RequestError as exc:
                raise WeatherAPIUnavailableError("Open-Meteo could not be reached.") from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                raise WeatherServiceError(f"Open-Meteo returned HTTP {status_code}.") from exc
            return response

    def to_thermal_input(
        self,
        raw_weather: dict[str, Any],
        age: int,
        personal_offset: float,
    ) -> ThermalInput:
        """Map an Open-Meteo response onto a domain thermal observation.

        ``temperature_2m`` becomes ``air_temp`` and ``apparent_temperature``
        becomes ``feels_like``, both in degrees Celsius.
        ``precipitation_probability`` becomes ``rain_prob`` (percent) and
        ``uv_index`` is copied unchanged. ``wind_speed_10m`` is kilometres
        per hour in the default Open-Meteo response and is converted to
        metres per second for :class:`ThermalInput`.

        ``relative_humidity_2m`` is part of the request contract. The domain
        model has no humidity field, so this mapper does not copy it.
        ``age`` and ``personal_offset`` come from the caller, not from the
        forecast.

        Args:
            raw_weather: Decoded body from :meth:`fetch_current_weather`.
            age: Wearer age in whole years.
            personal_offset: Preferred comfort shift in degrees Celsius.

        Returns:
            A validated thermal observation for the decision engine.

        Raises:
            WeatherServiceError: The ``current`` block or a required
                numeric field is missing or not a finite number.
        """
        current = raw_weather.get("current")
        if not isinstance(current, dict):
            raise WeatherServiceError("Open-Meteo payload is missing the current block.")
        wind_kmh = _required_float(current, "wind_speed_10m")
        return ThermalInput(
            air_temp=_required_float(current, "temperature_2m"),
            feels_like=_required_float(current, "apparent_temperature"),
            wind_speed=wind_kmh / KILOMETRES_PER_HOUR_PER_METRE_PER_SECOND,
            rain_prob=_required_float(current, "precipitation_probability"),
            uv_index=_required_float(current, "uv_index"),
            age=age,
            personal_offset=personal_offset,
            weather_code=_optional_weather_code(current),
        )

    async def _send(self, params: dict[str, float | str]) -> httpx.Response:
        """Issue the forecast GET with the 5.0 second timeout."""
        if self._client is not None:
            return await self._client.get(
                self._forecast_url,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        async with httpx.AsyncClient() as client:
            return await client.get(
                self._forecast_url,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )


def _diurnal_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pick the local 08:00, 14:00, and 20:00 samples from an hourly block."""
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise WeatherServiceError("Open-Meteo payload is missing the hourly block.")
    times = hourly.get("time")
    temperatures = hourly.get("temperature_2m")
    codes = hourly.get("weather_code")
    if not isinstance(times, list) or not isinstance(temperatures, list) or not isinstance(codes, list):
        raise WeatherServiceError("Open-Meteo hourly forecast is incomplete.")
    if not (len(times) == len(temperatures) == len(codes)):
        raise WeatherServiceError("Open-Meteo hourly forecast arrays differ in length.")
    samples: list[tuple[str, int, float, int]] = []
    for index, stamp in enumerate(times):
        parsed = _hour_stamp(stamp)
        if parsed is None:
            continue
        day, hour = parsed
        samples.append(
            (
                day,
                hour,
                _finite_number(temperatures[index], "temperature_2m"),
                int(_finite_number(codes[index], "weather_code")),
            )
        )
    if not samples:
        return []
    anchor = _anchor_day(samples)
    rows: list[dict[str, Any]] = []
    for name, target in _DIURNAL_TARGETS:
        chosen = _closest_hour(samples, anchor, target)
        if chosen is None:
            continue
        _day, _hour, temperature, code = chosen
        rows.append({"period": name, "temperature": temperature, "weather_code": code})
    return rows


def _hour_stamp(value: object) -> tuple[str, int] | None:
    """Return the local date and hour from an Open-Meteo timestamp."""
    if not isinstance(value, str) or "T" not in value:
        return None
    day, clock = value.split("T", 1)
    hour_text = clock.split(":", 1)[0]
    if not hour_text.isdigit():
        return None
    return day, int(hour_text)


def _anchor_day(samples: list[tuple[str, int, float, int]]) -> str:
    """Prefer the local date that contains the most target hours."""
    targets = {hour for _name, hour in _DIURNAL_TARGETS}
    coverage: dict[str, set[int]] = {}
    for day, hour, _temperature, _code in samples:
        coverage.setdefault(day, set()).add(hour)
    return max(coverage, key=lambda day: (len(coverage[day] & targets), day))


def _closest_hour(
    samples: list[tuple[str, int, float, int]],
    day: str,
    target: int,
) -> tuple[str, int, float, int] | None:
    """Return the exact target hour, or the nearest hour on that date."""
    same_day = [sample for sample in samples if sample[0] == day]
    if not same_day:
        return None
    exact = [sample for sample in same_day if sample[1] == target]
    if exact:
        return exact[0]
    return min(same_day, key=lambda sample: abs(sample[1] - target))

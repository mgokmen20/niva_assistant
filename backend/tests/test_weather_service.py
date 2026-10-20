"""Unit tests for the Open-Meteo weather service.

HTTP calls are served by ``httpx.MockTransport``. No test contacts the network.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.exceptions import WeatherAPIUnavailableError, WeatherServiceError
from app.core.constants import FORECAST_DAY_COUNT
from app.services.weather_service import (
    CURRENT_VARIABLES,
    DAILY_FORECAST_VARIABLES,
    DAILY_TRAVEL_VARIABLES,
    DEFAULT_OPEN_METEO_FORECAST_URL,
    REQUEST_TIMEOUT_SECONDS,
    TIMEZONE_AUTO,
    WEATHER_RETRY_BASE_DELAY_SECONDS,
    WEATHER_RETRY_COUNT,
    WeatherCache,
    WeatherService,
)

_LATITUDE: float = 46.948
_LONGITUDE: float = 7.4474
_Handler = Callable[[httpx.Request], httpx.Response]


def _sample_payload() -> dict[str, Any]:
    """Return a trimmed Open-Meteo forecast body with the fields Niva reads.

    ``wind_speed_10m`` is 18.0 because the provider default is kilometres
    per hour. 18 km/h is 5.0 m/s.
    """
    return {
        "latitude": _LATITUDE,
        "longitude": _LONGITUDE,
        "timezone": "Europe/Zurich",
        "current": {
            "time": "2026-10-13T12:00",
            "temperature_2m": 21.5,
            "apparent_temperature": 19.0,
            "relative_humidity_2m": 55,
            "wind_speed_10m": 18.0,
            "precipitation_probability": 40,
            "uv_index": 2.6,
        },
    }


class _RecordingClient(httpx.AsyncClient):
    """Async client that records the timeout and query sent by the service."""

    def __init__(self, handler: _Handler) -> None:
        super().__init__(transport=httpx.MockTransport(handler))
        self.requested_url: str | None = None
        self.requested_params: dict[str, Any] | None = None
        self.requested_timeout: float | httpx.Timeout | None = None
        self.call_count = 0

    async def get(
        self,
        url: str | httpx.URL,
        *,
        params: Any = None,
        timeout: float | httpx.Timeout | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Record the outgoing call, then let the mock transport answer it."""
        self.requested_url = str(url)
        self.requested_params = dict(params) if isinstance(params, dict) else None
        self.requested_timeout = timeout
        self.call_count += 1
        return await super().get(url, params=params, timeout=timeout, **kwargs)


async def _instant_sleep(delay: float) -> None:
    """Skip the real backoff delay and keep the retry schedule observable."""
    del delay


def _service(
    handler: _Handler,
    cache: WeatherCache | None = None,
    delays: list[float] | None = None,
) -> tuple[WeatherService, _RecordingClient]:
    """Pair a weather service with a client that cannot leave the process.

    Retries record their delays and return immediately so the suite does
    not wait on the production backoff.
    """

    async def record_sleep(delay: float) -> None:
        if delays is not None:
            delays.append(delay)

    client = _RecordingClient(handler)
    service = WeatherService(
        client=client,
        forecast_url=DEFAULT_OPEN_METEO_FORECAST_URL,
        cache=cache if cache is not None else WeatherCache(),
        sleeper=record_sleep if delays is not None else _instant_sleep,
    )
    return service, client


@pytest.mark.asyncio
async def test_fetch_current_weather_parses_open_meteo_response() -> None:
    """A mock forecast is requested with the Open-Meteo contract and mapped.

    The service must ask for the documented current variables and
    ``timezone=auto``, wait at most 5.0 seconds, and turn the ``current``
    block into a ``ThermalInput``. Wind is converted from km/h to m/s.
    Humidity stays on the raw payload because the domain model has no
    humidity field. Age and the personal offset come from the caller.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_sample_payload(), request=request)

    service, client = _service(handler)
    async with client:
        raw_weather = await service.fetch_current_weather(_LATITUDE, _LONGITUDE)
        thermal_input = service.to_thermal_input(raw_weather, age=8, personal_offset=1.5)

    assert client.requested_url == DEFAULT_OPEN_METEO_FORECAST_URL
    assert client.requested_timeout == REQUEST_TIMEOUT_SECONDS
    assert REQUEST_TIMEOUT_SECONDS == 5.0
    assert client.requested_params is not None
    assert client.requested_params["latitude"] == _LATITUDE
    assert client.requested_params["longitude"] == _LONGITUDE
    assert client.requested_params["current"] == CURRENT_VARIABLES
    assert client.requested_params["timezone"] == TIMEZONE_AUTO
    assert raw_weather["current"]["relative_humidity_2m"] == 55
    assert thermal_input.air_temp == 21.5
    assert thermal_input.feels_like == 19.0
    assert thermal_input.wind_speed == 5.0
    assert thermal_input.rain_prob == 40.0
    assert thermal_input.uv_index == 2.6
    assert thermal_input.age == 8
    assert thermal_input.personal_offset == 1.5


@pytest.mark.asyncio
async def test_fetch_current_weather_raises_when_open_meteo_times_out() -> None:
    """A mocked timeout becomes WeatherAPIUnavailableError, a WeatherServiceError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    service, client = _service(handler)
    async with client:
        with pytest.raises(WeatherAPIUnavailableError) as caught:
            await service.fetch_current_weather(_LATITUDE, _LONGITUDE)

    assert isinstance(caught.value, WeatherServiceError)
    assert caught.value.__cause__ is not None
    assert client.call_count == WEATHER_RETRY_COUNT + 1


@pytest.mark.asyncio
async def test_fetch_current_weather_raises_when_network_fails() -> None:
    """A mocked connection failure becomes WeatherAPIUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    service, client = _service(handler)
    async with client:
        with pytest.raises(WeatherServiceError) as caught:
            await service.fetch_current_weather(_LATITUDE, _LONGITUDE)

    assert isinstance(caught.value, WeatherAPIUnavailableError)
    assert client.call_count == WEATHER_RETRY_COUNT + 1


@pytest.mark.asyncio
async def test_fetch_current_weather_raises_when_status_is_not_successful() -> None:
    """An HTTP error status becomes WeatherServiceError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"reason": "unavailable"}, request=request)

    service, client = _service(handler)
    async with client:
        with pytest.raises(WeatherServiceError) as caught:
            await service.fetch_current_weather(_LATITUDE, _LONGITUDE)

    assert type(caught.value) is WeatherServiceError
    assert "503" in str(caught.value)
    assert client.call_count == 1


@pytest.mark.asyncio
async def test_fetch_current_weather_retries_timeouts_with_backoff() -> None:
    """Two timeouts are followed by a success, with delays of 0.25s then 0.5s."""
    delays: list[float] = []
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < WEATHER_RETRY_COUNT + 1:
            raise httpx.TimeoutException("timed out", request=request)
        return httpx.Response(200, json=_sample_payload(), request=request)

    service, client = _service(handler, delays=delays)
    async with client:
        payload = await service.fetch_current_weather(_LATITUDE, _LONGITUDE)

    assert payload["current"]["temperature_2m"] == 21.5
    assert client.call_count == WEATHER_RETRY_COUNT + 1
    assert delays == [
        WEATHER_RETRY_BASE_DELAY_SECONDS,
        WEATHER_RETRY_BASE_DELAY_SECONDS * 2,
    ]


@pytest.mark.asyncio
async def test_cached_forecast_skips_the_network_until_it_expires() -> None:
    """Rounded coordinates share one entry, and an expired entry is fetched again."""
    calls = {"count": 0}
    now = {"seconds": 0.0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=_sample_payload(), request=request)

    def clock() -> float:
        return now["seconds"]

    cache = WeatherCache(ttl_seconds=600.0, clock=clock)
    service, client = _service(handler, cache=cache)
    async with client:
        first = await service.fetch_current_weather(46.948, 7.4474)
        second = await service.fetch_current_weather(46.951, 7.449)
        now["seconds"] = 600.0
        third = await service.fetch_current_weather(46.948, 7.4474)

    assert calls["count"] == 2
    assert client.call_count == 2
    assert second["current"]["temperature_2m"] == first["current"]["temperature_2m"]
    assert third["current"]["temperature_2m"] == 21.5
    second["current"]["temperature_2m"] = 0
    cached_again = await service.fetch_current_weather(46.951, 7.449)
    assert cached_again["current"]["temperature_2m"] == 21.5


def _daily_payload() -> dict[str, Any]:
    """Return a seven-day Open-Meteo daily block."""
    return {
        "daily": {
            "time": [f"2026-10-{day:02d}" for day in range(19, 26)],
            "temperature_2m_max": [18.0, 17.0, 16.0, 15.0, 14.0, 13.0, 12.0],
            "temperature_2m_min": [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0],
            "precipitation_probability_max": [10, 20, 30, 40, 15, 5, 0],
            "weather_code": [0, 2, 3, 61, 1, 45, 95],
            "uv_index_max": [3.5, 2.0, 1.0, 4.0, 2.2, 1.1, 0.4],
            "wind_speed_10m_max": [18.0, 18.0, 18.0, 18.0, 18.0, 18.0, 18.0],
        }
    }


@pytest.mark.asyncio
async def test_fetch_daily_forecast_uses_daily_variables() -> None:
    """The seven-day read asks for daily fields and leaves the current cache alone."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_daily_payload(), request=request)

    service, client = _service(handler)
    async with client:
        current_cache = service._cache
        rows = await service.fetch_daily_forecast(_LATITUDE, _LONGITUDE)
        again = await service.fetch_daily_forecast(_LATITUDE, _LONGITUDE)

    assert FORECAST_DAY_COUNT == 7
    assert client.call_count == 1
    assert client.requested_params is not None
    assert client.requested_params["daily"] == DAILY_FORECAST_VARIABLES
    assert "current" not in client.requested_params
    assert client.requested_params["forecast_days"] == "7"
    assert client.requested_params["timezone"] == TIMEZONE_AUTO
    assert len(rows) == 7
    assert rows[0]["date"] == "2026-10-19"
    assert rows[0]["temperature_max"] == 18.0
    assert rows[0]["temperature_min"] == 8.0
    assert rows[3]["precipitation_probability"] == 40.0
    assert rows[3]["weather_code"] == 61
    assert "uv_index" not in rows[0]
    assert "wind_speed" not in rows[0]
    assert again[0]["temperature_max"] == 18.0
    assert current_cache.get(_LATITUDE, _LONGITUDE) is None


@pytest.mark.asyncio
async def test_daily_forecast_with_uv_does_not_replace_current_weather() -> None:
    """A travel fetch and a current fetch keep separate cache entries."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = str(request.url)
        if "daily=" in query:
            calls.append("daily")
            return httpx.Response(200, json=_daily_payload(), request=request)
        calls.append("current")
        return httpx.Response(200, json=_sample_payload(), request=request)

    service, client = _service(handler)
    async with client:
        await service.fetch_current_weather(_LATITUDE, _LONGITUDE)
        rows = await service.fetch_daily_forecast(_LATITUDE, _LONGITUDE, day_count=4, include_uv=True)
        await service.fetch_current_weather(_LATITUDE, _LONGITUDE)

    assert calls == ["current", "daily"]
    assert client.requested_params is not None
    assert client.requested_params["daily"] == DAILY_TRAVEL_VARIABLES
    assert rows[0]["uv_index"] == 3.5
    assert rows[0]["wind_speed"] == 5.0
    assert len(rows) == 7

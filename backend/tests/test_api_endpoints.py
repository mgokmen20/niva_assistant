"""API tests against the ASGI app. Weather and the database are mocked."""

from collections.abc import AsyncIterator
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from app.api.deps import get_optional_db, get_recommendation_service, get_weather_service
from app.core.config import Settings
from app.core.constants import ANALYTICS_BUCKET_ABOVE_15
from app.core.security import create_access_token
from app.main import app
from app.models.recommendation import RecommendationLog
from app.services.recommendation_service import RecommendationService
from app.services.weather_service import WeatherService

_FORECAST: dict[str, Any] = {
    "current": {
        "temperature_2m": 21.5,
        "apparent_temperature": 19.0,
        "relative_humidity_2m": 55,
        "wind_speed_10m": 18.0,
        "precipitation_probability": 40,
        "uv_index": 2.6,
    }
}


class _EmptyResult:
    """Query result for a wearer who is not in the stand-in session."""

    def scalar_one_or_none(self) -> None:
        """Report that the wearer baseline is missing."""
        return None

    def scalars(self) -> "_EmptyResult":
        """Return this result so ``scalars().all()`` is empty."""
        return self

    def all(self) -> list[object]:
        """Return no feedback rows."""
        return []


class _MemorySession:
    """Session stand-in that records added rows and never opens a database."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, entry: object) -> None:
        """Remember one staged ORM object."""
        self.added.append(entry)

    async def execute(self, _statement: object) -> "_EmptyResult":
        """Answer calibration lookups with no wearer row."""
        return _EmptyResult()

    async def flush(self) -> None:
        """Pretend the staged rows were sent to the database."""

    async def commit(self) -> None:
        """Pretend the transaction was committed."""

    async def rollback(self) -> None:
        """Pretend the transaction was rolled back."""

    async def close(self) -> None:
        """Pretend the session was closed."""


def _bearer() -> dict[str, str]:
    """Return a signed bearer header for one synthetic wearer."""
    token = create_access_token({"sub": str(uuid4())})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, _MemorySession]]:
    """Serve the app with mocked Open-Meteo weather and an in-memory session."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "daily=" in str(request.url):
            start = date.today()
            daily = {
                "daily": {
                    "time": [(start + timedelta(days=offset)).isoformat() for offset in range(7)],
                    "temperature_2m_max": [8.0, 14.0, 22.0, 24.0, 18.0, 16.0, 15.0],
                    "temperature_2m_min": [3.0, 10.0, 16.0, 18.0, 11.0, 9.0, 8.0],
                    "precipitation_probability_max": [10, 40, 0, 0, 5, 5, 5],
                    "weather_code": [3, 61, 0, 2, 3, 3, 3],
                    "uv_index_max": [1.0, 1.0, 1.0, 4.0, 2.0, 2.0, 2.0],
                    "wind_speed_10m_max": [18.0, 18.0, 18.0, 18.0, 18.0, 18.0, 18.0],
                }
            }
            return httpx.Response(200, json=daily, request=request)
        return httpx.Response(200, json=_FORECAST, request=request)

    weather_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setenv("SECRET_KEY", "test-signing-key")
    monkeypatch.setenv("ALGORITHM", "HS256")
    settings = Settings(
        CLOUDFLARE_ACCOUNT_ID="",
        CLOUDFLARE_API_TOKEN="",
        DATABASE_URL="",
        SECRET_KEY="test-signing-key",
        _env_file=None,
    )
    service = RecommendationService.create(
        WeatherService(client=weather_http),
        settings=settings,
    )
    memory_db = _MemorySession()

    async def override_recommendation_service() -> RecommendationService:
        return service

    async def override_optional_db() -> AsyncIterator[_MemorySession]:
        yield memory_db

    app.dependency_overrides[get_recommendation_service] = override_recommendation_service
    app.dependency_overrides[get_optional_db] = override_optional_db
    app.dependency_overrides[get_weather_service] = lambda: WeatherService(client=weather_http)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, memory_db
    app.dependency_overrides.clear()
    await weather_http.aclose()


@pytest.mark.asyncio
async def test_post_current_recommendation_returns_ok(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """A valid place returns clothing, weather, and a masked address log."""
    client, memory_db = api_client
    response = await client.post(
        "/api/v1/recommendations/current",
        headers=_bearer(),
        json={
            "latitude": 46.948,
            "longitude": 7.4474,
            "city_name": "Bern",
            "mode": "auto",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["effective_temperature"] == 19.0
    assert body["personal_offset"] == 0.0
    assert body["meteorology"]["air_temperature"] == 21.5
    assert body["meteorology"]["wind_speed"] == 5.0
    assert body["clothing_layers"]["base_layer"]["id"] == "light_t_shirt"
    assert body["voice_summary"]
    assert len(memory_db.added) == 1
    log = memory_db.added[0]
    assert isinstance(log, RecommendationLog)
    assert log.location_name == "Bern"
    assert log.client_ip_masked != "127.0.0.1"
    assert log.client_ip_masked in {"127.0.0.0", "unknown"}
    assert log.user_id is not None
    assert log.temperature_band == ANALYTICS_BUCKET_ABOVE_15
    assert log.recommended_layers["base_layer"]["id"] == "light_t_shirt"
    assert body["recommendation_id"] == str(log.id)


@pytest.mark.asyncio
async def test_post_current_recommendation_speaks_the_requested_language(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """The lang query selects the spoken summary without a model call."""
    client, _memory_db = api_client
    payload = {
        "latitude": 46.948,
        "longitude": 7.4474,
        "city_name": "Bern",
        "mode": "auto",
    }
    turkish = await client.post(
        "/api/v1/recommendations/current",
        params={"lang": "tr"},
        headers=_bearer(),
        json=payload,
    )
    german = await client.post(
        "/api/v1/recommendations/current",
        params={"lang": "de-CH"},
        headers=_bearer(),
        json=payload,
    )

    assert turkish.status_code == 200
    assert "konfor farkın" in turkish.json()["voice_summary"]
    assert german.status_code == 200
    german_summary = german.json()["voice_summary"]
    assert "Temperaturausgleich" in german_summary
    assert "ß" not in german_summary


@pytest.mark.asyncio
async def test_post_current_recommendation_rejects_invalid_coordinates(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """Latitude outside -90 to 90 is rejected before any weather call."""
    client, memory_db = api_client
    response = await client.post(
        "/api/v1/recommendations/current",
        headers=_bearer(),
        json={
            "latitude": 95,
            "longitude": 7.4474,
            "city_name": "Bern",
            "mode": "auto",
        },
    )

    assert response.status_code == 422
    assert memory_db.added == []


@pytest.mark.asyncio
async def test_warm_preference_shifts_temperature_and_adds_insulation(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """Warm mode lowers the decision temperature and adds a jacket, hat, and gloves."""
    client, _memory_db = api_client
    response = await client.post(
        "/api/v1/recommendations/current",
        headers=_bearer(),
        json={
            "latitude": 46.948,
            "longitude": 7.4474,
            "city_name": "Bern",
            "mode": "warm",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["effective_temperature"] == 17.0
    assert body["personal_offset"] == 0.0
    assert body["meteorology"]["air_temperature"] == 21.5
    assert body["clothing_layers"]["outer_layer"]["id"] == "waterproof_shell"
    accessory_ids = {item["id"] for item in body["clothing_layers"]["accessories"]}
    assert {"warm_hat", "gloves", "umbrella"} <= accessory_ids
    assert "warmer outfit" in body["voice_summary"]
    assert "feels like 17°C" in body["voice_summary"]


@pytest.mark.asyncio
async def test_light_preference_raises_the_decision_temperature(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """Light mode raises the decision temperature and keeps a mild outfit light."""
    client, _memory_db = api_client
    response = await client.post(
        "/api/v1/recommendations/current",
        headers=_bearer(),
        json={
            "latitude": 46.948,
            "longitude": 7.4474,
            "city_name": "Bern",
            "mode": "light",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["effective_temperature"] == 21.0
    assert body["clothing_layers"]["base_layer"]["id"] == "light_t_shirt"
    assert body["clothing_layers"]["mid_layer"] is None
    assert body["clothing_layers"]["outer_layer"]["id"] == "waterproof_shell"
    assert "lighter outfit" in body["voice_summary"]
    assert "feels like 21°C" in body["voice_summary"]


@pytest.mark.asyncio
async def test_guest_recommendation_is_rejected_before_clothing(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """A missing bearer token does not store an outfit or call for clothing."""
    client, memory_db = api_client
    response = await client.post(
        "/api/v1/recommendations/current",
        json={
            "latitude": 46.948,
            "longitude": 7.4474,
            "city_name": "Bern",
            "mode": "auto",
        },
    )

    assert response.status_code == 401
    assert memory_db.added == []


@pytest.mark.asyncio
async def test_weather_endpoint_returns_conditions_without_a_log(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """Open-Meteo conditions are public and do not write recommendation history."""
    client, memory_db = api_client
    response = await client.get(
        "/api/v1/weather/current",
        params={"latitude": 46.948, "longitude": 7.4474},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["air_temperature"] == 21.5
    assert body["apparent_temperature"] == 19.0
    assert body["wind_speed"] == 5.0
    assert "clothing_layers" not in body
    assert memory_db.added == []


@pytest.mark.asyncio
async def test_forecast_endpoint_returns_seven_days(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """The public strip is a daily forecast and does not log a recommendation."""
    client, memory_db = api_client
    response = await client.get(
        "/api/v1/weather/forecast",
        params={"latitude": 46.948, "longitude": 7.4474},
    )

    assert response.status_code == 200
    days = response.json()
    assert len(days) == 7
    assert days[0]["date"] == date.today().isoformat()
    assert "temperature_max" in days[0]
    assert "uv_index" not in days[0]
    assert memory_db.added == []


@pytest.mark.asyncio
async def test_travel_plan_requires_a_bearer(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
) -> None:
    """Guests cannot generate a packing list."""
    client, _memory_db = api_client
    today = date.today()
    response = await client.post(
        "/api/v1/travel/plan",
        json={
            "latitude": 46.948,
            "longitude": 7.4474,
            "city_name": "Bern",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=3)).isoformat(),
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_travel_plan_packs_the_signed_in_span(
    api_client: tuple[httpx.AsyncClient, _MemorySession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bearer receives base layers scaled to the trip and the extreme add-ons."""
    monkeypatch.setattr(
        "app.api.v1.endpoints_travel.get_settings",
        lambda: Settings(
            CLOUDFLARE_ACCOUNT_ID="",
            CLOUDFLARE_API_TOKEN="",
            SECRET_KEY="test-signing-key",
            _env_file=None,
        ),
    )
    client, memory_db = api_client
    today = date.today()
    response = await client.post(
        "/api/v1/travel/plan",
        params={"lang": "en"},
        headers=_bearer(),
        json={
            "latitude": 46.948,
            "longitude": 7.4474,
            "city_name": "Bern",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=3)).isoformat(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    quantities = {item["item_id"]: item["quantity"] for item in body["items"]}
    assert quantities["base_shirt"] == 4
    assert quantities["fleece"] == 1
    assert quantities["winter_coat"] == 1
    assert quantities["umbrella"] == 1
    assert "Pack 4 base shirts for Bern" in body["summary"]
    assert len(body["days"]) == 4
    assert body["days"][0]["date"] == today.isoformat()
    assert body["days"][0]["wind_speed"] == 5.0
    assert body["days"][0]["precipitation_probability"] == 10.0
    assert body["days"][1]["weather_code"] == 61
    assert memory_db.added == []

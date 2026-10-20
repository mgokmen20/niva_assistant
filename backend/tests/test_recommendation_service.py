"""Recommendation strategy tests. Cloudflare and Open-Meteo are mocked."""

import json
import logging
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.constants import (
    BASELINE_OFFSET_BALANCED_CELSIUS,
    BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS,
    CHILD_COLD_OFFSET_CELSIUS,
    STANDARD_CLOTHING_ITEMS,
    ClothingCategory,
)
from app.domain.thermal_engine import ThermalInput
from app.services.recommendation_providers import (
    CLEF_REQUEST_TIMEOUT_SECONDS,
    ClefRecommendationProvider,
    RuleBasedRecommendationProvider,
)
from app.services.recommendation_service import RecommendationService
from app.services.weather_service import WeatherService

_LATITUDE = 46.948
_LONGITUDE = 7.4474
_ACCOUNT_ID = "acct_123"
_API_TOKEN = "clef-token-value"
_CLEF_URL = (
    "https://api.cloudflare.com/client/v4/accounts/acct_123/ai/run/@cf/cloudflare/clef"
)


def _forecast() -> dict[str, Any]:
    """Return a mild Open-Meteo body. Wind is kilometres per hour."""
    return {
        "current": {
            "temperature_2m": 25.0,
            "apparent_temperature": 25.0,
            "relative_humidity_2m": 40,
            "wind_speed_10m": 0.0,
            "precipitation_probability": 0,
            "uv_index": 1.0,
        }
    }


def _adult_observation() -> ThermalInput:
    """Return the domain input that the mild forecast maps to for age 30."""
    return ThermalInput(
        air_temp=25.0,
        feels_like=25.0,
        wind_speed=0.0,
        rain_prob=0.0,
        uv_index=1.0,
        age=30,
        personal_offset=0.0,
    )


def _clef_answers(*, umbrella: float = 0.91, sunglasses: float = 0.5) -> dict[str, Any]:
    """Build a Clef answer map, including every accessory question."""
    answers: dict[str, Any] = {
        "base_layer": {"type": "choice", "choice": "thermal_base_layer", "confidence": 0.8},
        "mid_layer": {"type": "choice", "choice": "none", "confidence": 0.7},
        "outer_layer": {"type": "choice", "choice": "winter_coat", "confidence": 0.66},
        "risk_level": {"type": "choice", "choice": "high", "confidence": 0.9},
    }
    for item in STANDARD_CLOTHING_ITEMS:
        if item.category is not ClothingCategory.ACCESSORY:
            continue
        answers[item.id] = {"type": "noul", "noul": 0.1}
    answers["umbrella"]["noul"] = umbrella
    answers["sunglasses"]["noul"] = sunglasses
    return answers


def _clef_envelope(answers: dict[str, Any]) -> dict[str, Any]:
    """Wrap Clef answers in the Workers AI REST envelope."""
    return {
        "success": True,
        "errors": [],
        "result": {"model": "clef", "answers": answers, "usage": {"input_tokens": 120}},
    }


class _RecordingClient(httpx.AsyncClient):
    """Client that records POST calls and never leaves the process."""

    def __init__(self, handler: Any) -> None:
        super().__init__(transport=httpx.MockTransport(handler))
        self.calls: list[dict[str, Any]] = []

    async def post(
        self,
        url: str | httpx.URL,
        *,
        headers: Any = None,
        json: Any = None,
        timeout: float | httpx.Timeout | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Record the outgoing Clef call, then let the mock transport answer."""
        self.calls.append(
            {
                "url": str(url),
                "headers": dict(headers or {}),
                "json": json,
                "timeout": timeout,
            }
        )
        return await super().post(url, headers=headers, json=json, timeout=timeout, **kwargs)


def _weather_client() -> httpx.AsyncClient:
    """Return an Open-Meteo client backed by the mild forecast fixture."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_forecast(), request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_rule_based_recommendation_provider_returns_a_valid_payload() -> None:
    """A warm adult observation keeps a T-shirt, no coat, and low risk.

    The payload is the hot-weather ensemble plus a spoken summary.
    Effective temperature equals feels-like when age and offset add nothing.
    At 24°C and above the mid and outer slots stay empty and sunglasses
    are recommended.
    """
    provider = RuleBasedRecommendationProvider()
    result = await provider.generate_recommendation(_adult_observation(), _forecast())

    assert result["provider"] == "rule_based"
    assert result["effective_temperature_celsius"] == 25.0
    assert result["utci_category"] == "COMFORT"
    assert result["risk_level"] == "low"
    assert result["base_layer"]["id"] == "light_t_shirt"
    assert result["base_layer"]["category"] == "BASE"
    assert result["mid_layer"] is None
    assert result["outer_layer"] is None
    assert [item["id"] for item in result["accessories"]] == ["sunglasses"]
    assert result["voice_summary"].startswith("Hello there!")
    assert "clear skies" in result["voice_summary"]
    assert "light T-shirt" in result["voice_summary"]
    assert "before heading out." in result["voice_summary"]


def test_settings_load_cloudflare_credentials_only_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential fields follow the environment and stay out of repr."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", _API_TOKEN)
    settings = Settings(_env_file=None)

    assert settings.CLOUDFLARE_ACCOUNT_ID == "env-account"
    assert settings.CLOUDFLARE_API_TOKEN == _API_TOKEN
    assert _API_TOKEN not in repr(settings)

    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    empty = Settings(_env_file=None)
    assert empty.CLOUDFLARE_ACCOUNT_ID == ""
    assert empty.CLOUDFLARE_API_TOKEN == ""


@pytest.mark.asyncio
async def test_clef_recommendation_provider_parses_mocked_response() -> None:
    """A mocked Clef body becomes layers, accessories, and a high risk level.

    The request uses the Workers AI REST path, a bearer token, and typed
    questions. The token is not copied into the state or the recommendation.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_clef_envelope(_clef_answers()), request=request)

    settings = Settings(
        CLOUDFLARE_ACCOUNT_ID=_ACCOUNT_ID,
        CLOUDFLARE_API_TOKEN=_API_TOKEN,
    )
    client = _RecordingClient(handler)
    provider = ClefRecommendationProvider(settings=settings, client=client)
    async with client:
        result = await provider.generate_recommendation(_adult_observation(), _forecast())

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == _CLEF_URL
    assert call["timeout"] == CLEF_REQUEST_TIMEOUT_SECONDS
    assert call["headers"]["Authorization"] == f"Bearer {_API_TOKEN}"
    body = call["json"]
    assert body["model"] == "clef"
    assert body["state"]["air_temp_celsius"] == 25.0
    assert body["questions"]["base_layer"]["type"] == "choice"
    assert body["questions"]["mid_layer"]["type"] == "choice"
    assert body["questions"]["outer_layer"]["type"] == "choice"
    assert body["questions"]["risk_level"]["type"] == "choice"
    assert body["questions"]["umbrella"]["type"] == "noul"
    assert _API_TOKEN not in json.dumps(body["state"])
    assert result["provider"] == "clef"
    assert result["base_layer"]["id"] == "thermal_base_layer"
    assert result["mid_layer"] is None
    assert result["outer_layer"]["id"] == "winter_coat"
    assert result["risk_level"] == "high"
    assert [item["id"] for item in result["accessories"]] == ["umbrella", "sunglasses"]
    assert "winter coat" in result["voice_summary"]
    assert "Don't forget an umbrella!" in result["voice_summary"]
    assert _API_TOKEN not in json.dumps(result)


@pytest.mark.asyncio
async def test_recommendation_service_uses_rules_when_credentials_are_blank() -> None:
    """Blank Cloudflare settings skip Clef and still return a recommendation."""

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Cloudflare was called for {request.url}")

    weather_client = _weather_client()
    clef_client = _RecordingClient(explode)
    settings = Settings(CLOUDFLARE_ACCOUNT_ID="", CLOUDFLARE_API_TOKEN="")
    async with weather_client, clef_client:
        service = RecommendationService.create(
            WeatherService(client=weather_client),
            settings=settings,
            http_client=clef_client,
        )
        result = await service.get_recommendation(_LATITUDE, _LONGITUDE)

    assert clef_client.calls == []
    assert result["provider"] == "rule_based"
    assert result["base_layer"]["id"] == "light_t_shirt"
    assert result["voice_summary"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "warning_fragment"),
    [
        (
            lambda request: httpx.Response(500, json={"success": False}, request=request),
            "HTTP 500",
        ),
        (
            lambda request: (_ for _ in ()).throw(
                httpx.TimeoutException("timed out", request=request)
            ),
            "timed out",
        ),
    ],
)
async def test_clef_falls_back_when_cloudflare_fails(
    handler: Any,
    warning_fragment: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """HTTP 500 and timeouts succeed through the rule-based provider."""
    weather_client = _weather_client()
    clef_client = _RecordingClient(handler)
    settings = Settings(
        CLOUDFLARE_ACCOUNT_ID=_ACCOUNT_ID,
        CLOUDFLARE_API_TOKEN=_API_TOKEN,
    )
    observation = _adult_observation()
    expected = await RuleBasedRecommendationProvider().generate_recommendation(
        observation,
        _forecast(),
    )
    async with weather_client, clef_client:
        service = RecommendationService.create(
            WeatherService(client=weather_client),
            settings=settings,
            http_client=clef_client,
        )
        with caplog.at_level(logging.WARNING):
            result = await service.get_recommendation(_LATITUDE, _LONGITUDE)

    assert {key: result[key] for key in expected} == expected
    assert warning_fragment in caplog.text
    assert _API_TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_voice_summary_greets_a_named_wearer_in_the_city() -> None:
    """A morning forecast greets the signed-in wearer and names the city."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _forecast()
        payload["current"]["time"] = "2026-10-19T09:15"
        payload["current"]["precipitation_probability"] = 60
        payload["current"]["wind_speed_10m"] = 0.0
        return httpx.Response(200, json=payload, request=request)

    weather_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(CLOUDFLARE_ACCOUNT_ID="", CLOUDFLARE_API_TOKEN="")
    async with weather_client:
        service = RecommendationService.create(
            WeatherService(client=weather_client),
            settings=settings,
        )
        named = await service.get_recommendation(
            _LATITUDE,
            _LONGITUDE,
            city_name="Bern",
            first_name="Ada",
        )
        guest = await service.get_recommendation(_LATITUDE, _LONGITUDE, city_name="Bern")

    assert named["voice_summary"].startswith("Good morning Ada!")
    assert (
        "In Bern, the air temperature is 25°C, but it feels like 25°C with light rain today."
        in named["voice_summary"]
    )
    assert guest["voice_summary"].startswith("Hello there!")
    assert "Good morning" not in guest["voice_summary"]


def _subzero_observation(*, age: int, personal_offset: float) -> ThermalInput:
    """Air is mild. The apparent temperature is below freezing."""
    return ThermalInput(
        air_temp=13.7,
        feels_like=-1.5,
        wind_speed=2.0,
        rain_prob=0.0,
        uv_index=1.0,
        age=age,
        personal_offset=personal_offset,
        weather_code=3,
    )


def _insulation_rank(outfit: dict[str, Any]) -> tuple[int, int, int]:
    """Rank base, mid, and outer so a lighter outfit sorts first."""
    base_rank = {"light_t_shirt": 0, "long_sleeve_base": 1, "thermal_base_layer": 2}
    mid_rank = {
        "light_overshirt": 1,
        "cardigan": 2,
        "zip_hoodie": 2,
        "fleece_mid_layer": 3,
        "insulated_mid_layer": 4,
    }
    outer_rank = {"wind_shell": 1, "light_jacket": 2, "waterproof_shell": 3, "winter_coat": 4}

    def rank(table: dict[str, int], layer: object) -> int:
        if not isinstance(layer, dict):
            return 0
        garment_id = layer.get("id")
        if not isinstance(garment_id, str):
            return 0
        return table.get(garment_id, 0)

    return (
        rank(base_rank, outfit.get("base_layer")),
        rank(mid_rank, outfit.get("mid_layer")),
        rank(outer_rank, outfit.get("outer_layer")),
    )


@pytest.mark.asyncio
async def test_subzero_feels_like_keeps_a_cold_sensitive_child_at_least_as_warm() -> None:
    """13.7°C air and -1.5°C feels-like is a freezing outfit for both wearers.

    Feeling cold easily is stored as a negative comfort offset. Adding that
    offset lowers the decision temperature, so the child is dressed at least
    as warmly as the balanced adult. The mild air temperature does not
    select a light jacket.
    """
    provider = RuleBasedRecommendationProvider()
    forecast = _forecast()
    child = _subzero_observation(age=12, personal_offset=BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS)
    adult = _subzero_observation(age=40, personal_offset=BASELINE_OFFSET_BALANCED_CELSIUS)
    younger = _subzero_observation(age=11, personal_offset=BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS)
    child_outfit = await provider.generate_recommendation(child, forecast)
    adult_outfit = await provider.generate_recommendation(adult, forecast)
    younger_outfit = await provider.generate_recommendation(younger, forecast)

    assert child_outfit["effective_temperature_celsius"] == -1.5 + BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS
    assert adult_outfit["effective_temperature_celsius"] == -1.5
    assert child_outfit["effective_temperature_celsius"] < adult_outfit["effective_temperature_celsius"]
    assert younger_outfit["effective_temperature_celsius"] == (
        -1.5 + BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS - CHILD_COLD_OFFSET_CELSIUS
    )
    for outfit in (child_outfit, adult_outfit, younger_outfit):
        assert outfit["base_layer"]["id"] == "thermal_base_layer"
        assert outfit["mid_layer"]["id"] == "insulated_mid_layer"
        assert outfit["outer_layer"]["id"] == "winter_coat"
    assert _insulation_rank(child_outfit) >= _insulation_rank(adult_outfit)
    assert _insulation_rank(younger_outfit) >= _insulation_rank(adult_outfit)


@pytest.mark.asyncio
async def test_clef_cannot_replace_subzero_feels_like_with_a_light_jacket() -> None:
    """A Clef reply that follows the mild air temperature is raised to the rules."""
    answers = _clef_answers()
    answers["base_layer"]["choice"] = "light_t_shirt"
    answers["mid_layer"]["choice"] = "cardigan"
    answers["outer_layer"]["choice"] = "light_jacket"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_clef_envelope(answers), request=request)

    settings = Settings(CLOUDFLARE_ACCOUNT_ID=_ACCOUNT_ID, CLOUDFLARE_API_TOKEN=_API_TOKEN)
    client = _RecordingClient(handler)
    provider = ClefRecommendationProvider(settings=settings, client=client)
    async with client:
        result = await provider.generate_recommendation(
            _subzero_observation(age=40, personal_offset=BASELINE_OFFSET_BALANCED_CELSIUS),
            _forecast(),
        )

    assert result["provider"] == "clef"
    assert result["effective_temperature_celsius"] == -1.5
    assert result["base_layer"]["id"] == "thermal_base_layer"
    assert result["mid_layer"]["id"] == "insulated_mid_layer"
    assert result["outer_layer"]["id"] == "winter_coat"

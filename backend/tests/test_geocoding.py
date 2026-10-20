"""Geocoding search tests. HTTP calls stay inside the process."""

from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from app.api.deps import get_geocoding_service
from app.core.exceptions import GeocodingServiceError, GeocodingUnavailableError
from app.main import app
from app.services.geocoding_service import (
    DEFAULT_GEOCODING_SEARCH_URL,
    NOMINATIM_USER_AGENT,
    REQUEST_TIMEOUT_SECONDS,
    REVERSE_LOOKUP_TIMEOUT_SECONDS,
    GeocodingService,
)


def _bern() -> dict[str, Any]:
    """Return one Open-Meteo geocoding row for Bern."""
    return {
        "id": 2661552,
        "name": "Bern",
        "latitude": 46.94809,
        "longitude": 7.44744,
        "admin1": "Bern",
        "country": "Switzerland",
    }


def _service(handler: Any) -> tuple[GeocodingService, httpx.AsyncClient]:
    """Pair the service with a mock transport."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeocodingService(client=client, search_url=DEFAULT_GEOCODING_SEARCH_URL), client


@pytest.mark.asyncio
async def test_search_maps_open_meteo_results_and_skips_incomplete_rows() -> None:
    """A mock search asks for five English JSON matches and drops a bad row."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["name"] == "Bern"
        assert request.url.params["count"] == "5"
        assert request.url.params["language"] == "en"
        assert request.url.params["format"] == "json"
        body = {
            "results": [
                _bern(),
                {"id": 1, "name": "Missing coordinates"},
                {"id": 2, "name": "No region", "latitude": 47.0, "longitude": 8.0, "country": "Switzerland"},
            ]
        }
        return httpx.Response(200, json=body, request=request)

    service, client = _service(handler)
    async with client:
        matches = await service.search(" Bern ")

    assert matches[0]["name"] == "Bern"
    assert matches[0]["admin1"] == "Bern"
    assert matches[0]["country"] == "Switzerland"
    assert matches[1]["admin1"] is None
    assert matches[1]["latitude"] == 47.0
    assert len(matches) == 2


@pytest.mark.asyncio
async def test_search_returns_an_empty_list_when_results_are_missing() -> None:
    """A body without a results array is a successful empty search."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"generationtime_ms": 0.1}, request=request)

    service, client = _service(handler)
    async with client:
        assert await service.search("Zz") == []


@pytest.mark.asyncio
async def test_search_raises_when_geocoding_times_out() -> None:
    """A timeout becomes GeocodingUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    service, client = _service(handler)
    async with client:
        with pytest.raises(GeocodingUnavailableError) as caught:
            await service.search("Bern")

    assert isinstance(caught.value, GeocodingServiceError)
    assert REQUEST_TIMEOUT_SECONDS == 15.0


@pytest.mark.asyncio
async def test_location_search_endpoint_returns_matches() -> None:
    """GET /locations/search returns the mapped place list."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [_bern()]}, request=request)

    service, upstream = _service(handler)

    def override() -> GeocodingService:
        return service

    app.dependency_overrides[get_geocoding_service] = override
    transport = ASGITransport(app=app)
    try:
        async with upstream, httpx.AsyncClient(transport=transport, base_url="http://test") as api:
            response = await api.get("/api/v1/locations/search", params={"query": "Bern"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": 2661552,
            "name": "Bern",
            "latitude": 46.94809,
            "longitude": 7.44744,
            "admin1": "Bern",
            "country": "Switzerland",
        }
    ]


@pytest.mark.asyncio
async def test_location_search_rejects_a_short_query() -> None:
    """A one-character query is rejected before a geocoding call."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        response = await api.get("/api/v1/locations/search", params={"query": "B"})

    assert response.status_code == 422


def _reverse_service(handler: Any) -> tuple[GeocodingService, httpx.AsyncClient]:
    """Pair reverse lookup with a mock transport on the real provider URLs."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeocodingService(client=client), client


@pytest.mark.asyncio
async def test_reverse_reads_nominatim_town_and_sends_the_required_user_agent() -> None:
    """Nominatim town and state become the settlement, with the Niva user agent."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == NOMINATIM_USER_AGENT
        assert request.url.params["zoom"] == "14"
        assert request.url.params["addressdetails"] == "1"
        body = {
            "display_name": "Münsingen, Bern-Mittelland, Bern, Switzerland",
            "address": {
                "village": "Münsingen",
                "state": "Bern",
                "country": "Switzerland",
            },
        }
        return httpx.Response(200, json=body, request=request)

    service, client = _reverse_service(handler)
    async with client:
        place = await service.reverse(46.8732, 7.5621)

    assert place["name"] == "Münsingen"
    assert place["region"] == "Bern"
    assert place["country"] == "Switzerland"
    assert place["display_name"] == "Münsingen, Bern-Mittelland, Bern, Switzerland"


@pytest.mark.asyncio
async def test_reverse_falls_back_to_bigdatacloud_when_nominatim_times_out() -> None:
    """A Nominatim timeout uses the BigDataCloud city and canton."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim.openstreetmap.org" in str(request.url):
            raise httpx.TimeoutException("timed out", request=request)
        assert "bigdatacloud.net" in str(request.url)
        assert request.url.params["localityLanguage"] == "en"
        return httpx.Response(
            200,
            json={
                "city": "Münsingen",
                "principalSubdivision": "Bern",
                "countryName": "Switzerland",
            },
            request=request,
        )

    service, client = _reverse_service(handler)
    async with client:
        place = await service.reverse(46.8732, 7.5621)

    assert place == {
        "name": "Münsingen",
        "region": "Bern",
        "country": "Switzerland",
        "display_name": "Münsingen, Bern, Switzerland",
    }
    assert REVERSE_LOOKUP_TIMEOUT_SECONDS == 5.0


@pytest.mark.asyncio
async def test_reverse_raises_when_both_providers_fail() -> None:
    """Neither provider answering becomes GeocodingUnavailableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    service, client = _reverse_service(handler)
    async with client:
        with pytest.raises(GeocodingUnavailableError):
            await service.reverse(46.8732, 7.5621)


@pytest.mark.asyncio
async def test_reverse_endpoint_returns_the_settlement() -> None:
    """GET /locations/reverse returns the mapped place."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "display_name": "Bern, Switzerland",
                "address": {"city": "Bern", "state": "Bern", "country": "Switzerland"},
            },
            request=request,
        )

    service, upstream = _reverse_service(handler)

    def override() -> GeocodingService:
        return service

    app.dependency_overrides[get_geocoding_service] = override
    transport = ASGITransport(app=app)
    try:
        async with upstream, httpx.AsyncClient(transport=transport, base_url="http://test") as api:
            response = await api.get(
                "/api/v1/locations/reverse",
                params={"lat": 46.948, "lon": 7.4474},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["name"] == "Bern"
    assert response.json()["region"] == "Bern"
    assert response.json()["country"] == "Switzerland"

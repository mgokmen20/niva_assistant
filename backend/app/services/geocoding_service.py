"""Async client for place search and reverse geocoding.

Name search uses Open-Meteo. A GPS coordinate is resolved with Nominatim,
then BigDataCloud when Nominatim does not answer. The service does not
choose clothing and it does not import a web framework.
"""

import math
from typing import Any, Final

import httpx

from ..core.exceptions import GeocodingServiceError, GeocodingUnavailableError

# Geocoding replies are often slower than the forecast endpoint.
REQUEST_TIMEOUT_SECONDS: Final[float] = 15.0
DEFAULT_GEOCODING_SEARCH_URL: Final[str] = "https://geocoding-api.open-meteo.com/v1/search"
RESULT_LIMIT: Final[int] = 5
RESULT_LANGUAGE: Final[str] = "en"
RESULT_FORMAT: Final[str] = "json"
NOMINATIM_REVERSE_URL: Final[str] = "https://nominatim.openstreetmap.org/reverse"
BIGDATACLOUD_REVERSE_URL: Final[str] = (
    "https://api.bigdatacloud.net/data/reverse-geocode-client"
)
NOMINATIM_USER_AGENT: Final[str] = "NivaWeatherApp/1.0"
# The two reverse calls share one 5 second budget so a slow Nominatim
# response still leaves time for the fallback.
NOMINATIM_TIMEOUT_SECONDS: Final[float] = 3.0
BIGDATACLOUD_TIMEOUT_SECONDS: Final[float] = 2.0
REVERSE_LOOKUP_TIMEOUT_SECONDS: Final[float] = (
    NOMINATIM_TIMEOUT_SECONDS + BIGDATACLOUD_TIMEOUT_SECONDS
)
NOMINATIM_ZOOM: Final[int] = 14
SETTLEMENT_ADDRESS_FIELDS: Final[tuple[str, ...]] = (
    "city",
    "town",
    "village",
    "municipality",
    "suburb",
)
REGION_ADDRESS_FIELDS: Final[tuple[str, ...]] = ("state", "county", "admin1")


class GeocodingService:
    """Search Open-Meteo for a short list of matching places."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        search_url: str | None = None,
        nominatim_url: str | None = None,
        bigdatacloud_url: str | None = None,
    ) -> None:
        """Store the HTTP client and the geocoding endpoints.

        Args:
            client: Optional async client. The service does not close a
                client it did not create.
            search_url: Open-Meteo search URL. Tests can point this at a
                fake host.
            nominatim_url: Nominatim reverse URL.
            bigdatacloud_url: BigDataCloud reverse URL.
        """
        self._client = client
        self._search_url = search_url or DEFAULT_GEOCODING_SEARCH_URL
        self._nominatim_url = nominatim_url or NOMINATIM_REVERSE_URL
        self._bigdatacloud_url = bigdatacloud_url or BIGDATACLOUD_REVERSE_URL

    async def search(self, query: str) -> list[dict[str, Any]]:
        """Return up to five places whose name matches ``query``.

        The request uses ``count=5``, ``language=en``, and ``format=json``.
        A timeout or a transport failure raises
        :class:`GeocodingUnavailableError`. An HTTP error status or a body
        that is not JSON raises :class:`GeocodingServiceError`. A response
        with no ``results`` array is an empty match list.

        Args:
            query: Place name typed by the wearer. Surrounding spaces are
                ignored.

        Returns:
            Match dictionaries with id, name, latitude, longitude, admin1,
            and country. Incomplete rows are dropped.
        """
        name = query.strip()
        params: dict[str, str | int] = {
            "name": name,
            "count": RESULT_LIMIT,
            "language": RESULT_LANGUAGE,
            "format": RESULT_FORMAT,
        }
        try:
            response = await self._send(params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise GeocodingUnavailableError("Open-Meteo geocoding timed out.") from exc
        except httpx.RequestError as exc:
            raise GeocodingUnavailableError("Open-Meteo geocoding could not be reached.") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise GeocodingServiceError(f"Open-Meteo geocoding returned HTTP {status_code}.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GeocodingServiceError("Open-Meteo geocoding returned a body that is not JSON.") from exc
        if not isinstance(payload, dict):
            raise GeocodingServiceError("Open-Meteo geocoding returned a JSON value that is not an object.")
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        matches: list[dict[str, Any]] = []
        for row in results:
            match = _match_from_row(row)
            if match is not None:
                matches.append(match)
            if len(matches) >= RESULT_LIMIT:
                break
        return matches

    async def reverse(self, latitude: float, longitude: float) -> dict[str, str]:
        """Resolve a coordinate to a settlement name.

        Nominatim is tried first, with ``User-Agent: NivaWeatherApp/1.0``.
        A timeout, a transport error, an HTTP error, or a body without a
        settlement falls through to BigDataCloud. When both fail, this
        raises :class:`GeocodingUnavailableError`.

        Args:
            latitude: Degrees north, from -90 to 90.
            longitude: Degrees east, from -180 to 180.

        Returns:
            ``name``, ``region``, ``country``, and ``display_name``.
            Missing optional parts are empty strings.
        """
        place = await self._reverse_nominatim(latitude, longitude)
        if place is None:
            place = await self._reverse_bigdatacloud(latitude, longitude)
        if place is None:
            raise GeocodingUnavailableError("Reverse geocoding did not return a place.")
        return place

    async def _reverse_nominatim(self, latitude: float, longitude: float) -> dict[str, str] | None:
        """Ask Nominatim for the settlement, or return None when it cannot."""
        params: dict[str, str | int | float] = {
            "lat": latitude,
            "lon": longitude,
            "format": "json",
            "zoom": NOMINATIM_ZOOM,
            "addressdetails": 1,
        }
        headers = {
            "User-Agent": NOMINATIM_USER_AGENT,
            "Accept-Language": "en",
        }
        payload = await self._read_json(self._nominatim_url, params, NOMINATIM_TIMEOUT_SECONDS, headers)
        if payload is None:
            return None
        return _place_from_nominatim(payload)

    async def _reverse_bigdatacloud(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, str] | None:
        """Ask BigDataCloud for the settlement, or return None when it cannot."""
        params: dict[str, str | int | float] = {
            "latitude": latitude,
            "longitude": longitude,
            "localityLanguage": "en",
        }
        payload = await self._read_json(
            self._bigdatacloud_url,
            params,
            BIGDATACLOUD_TIMEOUT_SECONDS,
            None,
        )
        if payload is None:
            return None
        return _place_from_bigdatacloud(payload)

    async def _read_json(
        self,
        url: str,
        params: dict[str, str | int | float],
        timeout: float,
        headers: dict[str, str] | None,
    ) -> dict[str, Any] | None:
        """GET JSON, or return None when the call cannot be used."""
        try:
            response = await self._get(url, params, timeout, headers)
            response.raise_for_status()
            payload = response.json()
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    async def _send(self, params: dict[str, str | int]) -> httpx.Response:
        """Issue the search GET with the 15 second timeout."""
        return await self._get(self._search_url, params, REQUEST_TIMEOUT_SECONDS, None)

    async def _get(
        self,
        url: str,
        params: dict[str, str | int | float],
        timeout: float,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        """Issue one GET with the given timeout and optional headers."""
        if self._client is not None:
            return await self._client.get(url, params=params, timeout=timeout, headers=headers)
        async with httpx.AsyncClient() as client:
            return await client.get(url, params=params, timeout=timeout, headers=headers)


def _match_from_row(row: Any) -> dict[str, Any] | None:
    """Copy one geocoding row, or return None when a required field is unusable."""
    if not isinstance(row, dict):
        return None
    place_id = row.get("id")
    name = row.get("name")
    latitude = row.get("latitude")
    longitude = row.get("longitude")
    if isinstance(place_id, bool) or not isinstance(place_id, int):
        return None
    if not isinstance(name, str) or name.strip() == "":
        return None
    if not _is_coordinate(latitude) or not _is_coordinate(longitude):
        return None
    return {
        "id": place_id,
        "name": name.strip(),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "admin1": _optional_text(row.get("admin1")),
        "country": _optional_text(row.get("country")),
    }


def _place_from_nominatim(payload: dict[str, Any]) -> dict[str, str] | None:
    """Read a settlement from a Nominatim reverse body."""
    address = payload.get("address")
    if not isinstance(address, dict):
        return None
    name = _first_address_field(address, SETTLEMENT_ADDRESS_FIELDS)
    if name == "":
        return None
    region = _first_address_field(address, REGION_ADDRESS_FIELDS)
    country = _first_address_field(address, ("country",))
    provided = payload.get("display_name")
    display_name = provided.strip() if isinstance(provided, str) and provided.strip() != "" else ""
    return {
        "name": name,
        "region": region,
        "country": country,
        "display_name": display_name or _composed_display(name, region, country),
    }


def _place_from_bigdatacloud(payload: dict[str, Any]) -> dict[str, str] | None:
    """Read a settlement from a BigDataCloud reverse body."""
    name = _first_address_field(payload, ("city", "locality"))
    if name == "":
        return None
    region = _first_address_field(payload, ("principalSubdivision",))
    country = _first_address_field(payload, ("countryName",))
    return {
        "name": name,
        "region": region,
        "country": country,
        "display_name": _composed_display(name, region, country),
    }


def _first_address_field(source: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Return the first non-blank text field, or an empty string."""
    for field_name in fields:
        value = source.get(field_name)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
    return ""


def _composed_display(name: str, region: str, country: str) -> str:
    """Join the place parts that are present."""
    return ", ".join(part for part in (name, region, country) if part != "")


def _optional_text(value: Any) -> str | None:
    """Return stripped text, or None when the provider omitted the field."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text == "":
        return None
    return text


def _is_coordinate(value: Any) -> bool:
    """Return whether ``value`` is a finite number of degrees."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))

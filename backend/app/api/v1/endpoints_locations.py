"""Place-name search routes.

Handlers parse the query, call the geocoding service, and map the DTO.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.exceptions import GeocodingServiceError, GeocodingUnavailableError
from ...schemas.location_schema import LocationMatch, ReverseLocation
from ...services.geocoding_service import GeocodingService
from ..deps import get_geocoding_service

router = APIRouter(prefix="/locations", tags=["locations"])

MIN_QUERY_LENGTH = 2


@router.get("/search", response_model=list[LocationMatch])
async def search_locations(
    query: str = Query(min_length=MIN_QUERY_LENGTH, max_length=80),
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
) -> list[LocationMatch]:
    """Return up to five places matching the typed name.

    The query is forwarded to Open-Meteo geocoding. A blank query after
    trimming is rejected. Timeouts become status 503.
    """
    name = query.strip()
    if len(name) < MIN_QUERY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must be at least 2 characters.",
        )
    try:
        matches = await geocoding_service.search(name)
    except GeocodingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location search is unavailable.",
        ) from exc
    except GeocodingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Location search failed.",
        ) from exc
    return [LocationMatch.model_validate(match) for match in matches]


@router.get("/reverse", response_model=ReverseLocation)
async def reverse_location(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
) -> ReverseLocation:
    """Return the settlement for a GPS coordinate.

    Nominatim is tried first. BigDataCloud is used when Nominatim times
    out or cannot name a settlement. The lookup budget is 5 seconds.
    """
    try:
        place = await geocoding_service.reverse(lat, lon)
    except GeocodingUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location lookup is unavailable.",
        ) from exc
    except GeocodingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Location lookup failed.",
        ) from exc
    return ReverseLocation.model_validate(place)

"""Authenticated trip packing routes.

The handler checks the bearer, asks the travel engine for a plan, and
maps domain errors onto HTTP status codes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.exceptions import WeatherAPIUnavailableError, WeatherServiceError

from ...schemas.travel_schema import (
    PackingItemResponse,
    SaveTripRequest,
    SavedTripResponse,
    TravelPlanRequest,
    TravelPlanResponse,
    TripOutlookDay,
    UpdateTripItemsRequest,
)
from ...services.travel_engine import TravelWindowError, build_travel_plan, travel_window_detail
from ...services.trip_service import TripService
from ...services.tts_service import normalize_language
from ...services.weather_service import WeatherService
from ..deps import get_current_user_id, get_db, get_weather_service

_trips = TripService()

router = APIRouter(prefix="/travel", tags=["travel"])


@router.post("/plan", response_model=TravelPlanResponse)
async def create_travel_plan(
    body: TravelPlanRequest,
    lang: str = Query(default="en"),
    _user_id: UUID = Depends(get_current_user_id),
    weather_service: WeatherService = Depends(get_weather_service),
) -> TravelPlanResponse:
    """Pack one destination for a signed-in wearer."""
    try:
        plan = await build_travel_plan(
            weather_service=weather_service,
            latitude=body.latitude,
            longitude=body.longitude,
            city_name=body.city_name,
            start=body.start_date,
            end=body.end_date,
            language=normalize_language(lang),
            settings=get_settings(),
        )
    except TravelWindowError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=travel_window_detail(exc.code),
        ) from exc
    except WeatherAPIUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service is unavailable.",
        ) from exc
    except WeatherServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Weather service failed.",
        ) from exc
    return TravelPlanResponse(
        city_name=plan.city_name,
        start_date=plan.start_date,
        end_date=plan.end_date,
        summary=plan.summary,
        items=[
            PackingItemResponse(item_id=item.item_id, category=item.category, quantity=item.quantity)
            for item in plan.items
        ],
        days=[
            TripOutlookDay(
                date=day.date,
                temperature_max=day.temperature_max_c,
                temperature_min=day.temperature_min_c,
                precipitation_probability=day.precipitation_probability,
                weather_code=day.weather_code,
                wind_speed=day.wind_speed_mps,
            )
            for day in plan.days
        ],
    )


@router.post("/trips", response_model=SavedTripResponse, status_code=status.HTTP_201_CREATED)
async def save_trip(
    body: SaveTripRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SavedTripResponse:
    """Store the current packing plan for the signed-in wearer."""
    trip = await _trips.create_trip(
        db,
        user_id=user_id,
        destination_city=body.destination_city,
        start_date=body.start_date,
        end_date=body.end_date,
        summary_text=body.summary_text,
        packing_items=[item.model_dump() for item in body.packing_items],
    )
    return SavedTripResponse.model_validate(trip, from_attributes=True)


@router.get("/trips", response_model=list[SavedTripResponse])
async def list_trips(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[SavedTripResponse]:
    """Return the wearer's saved trips, latest start date first."""
    trips = await _trips.list_trips(db, user_id)
    return [SavedTripResponse.model_validate(trip, from_attributes=True) for trip in trips]


@router.patch("/trips/{trip_id}/items", response_model=SavedTripResponse)
async def update_trip_items(
    trip_id: UUID,
    body: UpdateTripItemsRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SavedTripResponse:
    """Tick or untick packing items on one owned trip."""
    trip = await _trips.update_checks(
        db,
        user_id=user_id,
        trip_id=trip_id,
        checks={item.id: item.checked for item in body.items},
    )
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip was not found.")
    return SavedTripResponse.model_validate(trip, from_attributes=True)


@router.delete("/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove one saved trip that belongs to the signed-in wearer."""
    deleted = await _trips.delete_trip(db, user_id=user_id, trip_id=trip_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip was not found.")

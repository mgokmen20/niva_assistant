"""Public weather routes.

Handlers read coordinates and return the current Open-Meteo observation.
Clothing, voice, and recommendation history stay on their own routes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.constants import FORECAST_DAY_COUNT
from ...core.exceptions import WeatherAPIUnavailableError, WeatherServiceError
from ...schemas.forecast_schema import DailyForecastDay
from ...schemas.recommendation_schema import Meteorology
from ...services.weather_service import WeatherService
from ..deps import get_weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/current", response_model=Meteorology)
async def read_current_weather(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    weather_service: WeatherService = Depends(get_weather_service),
) -> Meteorology:
    """Return the current air, wind, rain, and UV observation for one place."""
    try:
        payload = await weather_service.current_meteorology(latitude, longitude)
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
    return Meteorology.model_validate(payload)


@router.get("/forecast", response_model=list[DailyForecastDay])
async def read_daily_forecast(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    weather_service: WeatherService = Depends(get_weather_service),
) -> list[DailyForecastDay]:
    """Return seven daily highs, lows, rain chances, and weather codes."""
    try:
        rows = await weather_service.fetch_daily_forecast(
            latitude,
            longitude,
            day_count=FORECAST_DAY_COUNT,
            include_uv=False,
        )
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
    return [DailyForecastDay.model_validate(row) for row in rows]

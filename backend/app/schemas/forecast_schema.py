"""Daily forecast rows returned by the public weather route."""

from pydantic import BaseModel, Field


class DailyForecastDay(BaseModel):
    """One local day from the Open-Meteo daily block."""

    date: str = Field(min_length=10, max_length=10)
    temperature_max: float
    temperature_min: float
    precipitation_probability: float
    weather_code: int

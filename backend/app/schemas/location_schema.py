"""HTTP models for city search."""

from pydantic import BaseModel, ConfigDict


class LocationMatch(BaseModel):
    """One place returned by the geocoding search."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    latitude: float
    longitude: float
    admin1: str | None = None
    country: str | None = None


class ReverseLocation(BaseModel):
    """Settlement resolved from a GPS coordinate."""

    model_config = ConfigDict(extra="ignore")

    name: str
    region: str
    country: str
    display_name: str

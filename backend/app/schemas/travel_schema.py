"""Request and response models for the trip packing planner."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_PACKING_CATEGORIES = frozenset({"base", "mid", "outer", "accessory"})


class TravelPlanRequest(BaseModel):
    """Destination and inclusive dates for one packing plan."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    city_name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date

    @field_validator("city_name")
    @classmethod
    def strip_city_name(cls, value: str) -> str:
        """Reject a blank place name after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text


class TripOutlookDay(BaseModel):
    """One day of the trip, in the same units the home page already uses."""

    date: str
    temperature_max: float
    temperature_min: float
    precipitation_probability: float
    weather_code: int
    wind_speed: float


class PackingItemResponse(BaseModel):
    """One checklist row the wearer can tick off while packing."""

    item_id: str
    category: str
    quantity: int = Field(ge=1)


class TravelPlanResponse(BaseModel):
    """Packing list and the two-sentence trip brief."""

    city_name: str
    start_date: str
    end_date: str
    summary: str
    items: list[PackingItemResponse]
    days: list[TripOutlookDay]


class SavedPackingItem(BaseModel):
    """One stored checklist row, including the localized name and tick."""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    category: str
    quantity: int = Field(ge=1, le=99)
    checked: bool = False

    @field_validator("id", "name", "category")
    @classmethod
    def strip_item_text(cls, value: str) -> str:
        """Reject blank item text after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text

    @field_validator("category")
    @classmethod
    def known_category(cls, value: str) -> str:
        """Keep the four packing categories the planner already uses."""
        if value not in _PACKING_CATEGORIES:
            raise ValueError("Category must be base, mid, outer, or accessory.")
        return value


class SaveTripRequest(BaseModel):
    """A finished plan the wearer wants to keep."""

    destination_city: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    summary_text: str = Field(min_length=1, max_length=4000)
    packing_items: list[SavedPackingItem] = Field(min_length=1, max_length=40)

    @field_validator("destination_city", "summary_text")
    @classmethod
    def strip_trip_text(cls, value: str) -> str:
        """Reject blank trip text after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text


class TripItemCheck(BaseModel):
    """One checkbox change inside a saved trip."""

    id: str = Field(min_length=1, max_length=64)
    checked: bool

    @field_validator("id")
    @classmethod
    def strip_id(cls, value: str) -> str:
        """Reject a blank item id."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text


class UpdateTripItemsRequest(BaseModel):
    """Checkbox updates for one saved trip."""

    items: list[TripItemCheck] = Field(min_length=1, max_length=40)


class SavedTripResponse(BaseModel):
    """One saved trip returned to its owner."""

    id: UUID
    destination_city: str
    start_date: date
    end_date: date
    summary_text: str
    packing_items: list[SavedPackingItem]
    created_at: datetime

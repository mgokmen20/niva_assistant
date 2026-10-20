"""HTTP request and response models for recommendations and feedback."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..services.feedback_service import ALLOWED_THERMAL_RATINGS
from ..services.outfit_preference import normalize_outfit_preference


class RecommendationRequest(BaseModel):
    """Coordinates and place name for a current clothing recommendation."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    city_name: str = Field(min_length=1, max_length=120)
    mode: str = Field(min_length=1, max_length=32)
    first_name: str | None = Field(default=None, max_length=80)

    @field_validator("city_name")
    @classmethod
    def strip_city_name(cls, value: str) -> str:
        """Reject a blank place name after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text

    @field_validator("mode")
    @classmethod
    def mode_must_be_known(cls, value: str) -> str:
        """Keep light, balanced, warm, and the historical auto alias."""
        return normalize_outfit_preference(value)

    @field_validator("first_name")
    @classmethod
    def strip_first_name(cls, value: str | None) -> str | None:
        """Keep a signed-in given name, and treat a blank name as a guest."""
        if value is None:
            return None
        text = value.strip()
        if text == "":
            return None
        return text


class FeedbackRequest(BaseModel):
    """Wearer rating for one stored recommendation."""

    recommendation_id: UUID
    rating: str
    followed_recommendation: bool

    @field_validator("rating")
    @classmethod
    def rating_must_be_allowed(cls, value: str) -> str:
        """Keep only the thermal ratings the feedback service understands."""
        normalized = value.strip().upper()
        if normalized not in ALLOWED_THERMAL_RATINGS:
            allowed = ", ".join(sorted(ALLOWED_THERMAL_RATINGS))
            raise ValueError(f"Rating must be one of: {allowed}.")
        return normalized


class DiurnalPeriod(BaseModel):
    """One local daytime sample: morning, afternoon, or evening."""

    period: str
    temperature: float
    weather_code: int


class Meteorology(BaseModel):
    """Observed conditions used for the clothing decision."""

    air_temperature: float
    apparent_temperature: float
    wind_speed: float
    rain_probability: float
    uv_index: float
    diurnal: list[DiurnalPeriod] = Field(default_factory=list)


class Garment(BaseModel):
    """One recommended garment or accessory."""

    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    category: str
    removable: bool | None = None


class ClothingLayers(BaseModel):
    """Layered outfit returned by a recommendation provider."""

    base_layer: Garment
    mid_layer: Garment | None = None
    outer_layer: Garment | None = None
    accessories: list[Garment]
    risk_level: str
    utci_category: str


class RecommendationResponse(BaseModel):
    """Client payload for one current recommendation."""

    recommendation_id: UUID | None = None
    effective_temperature: float
    meteorology: Meteorology
    clothing_layers: ClothingLayers
    voice_summary: str
    personal_offset: float | None = None


class FeedbackResponse(BaseModel):
    """Offset change recorded after one rating."""

    previous_offset: float
    new_offset: float
    delta_applied: float


def clothing_layers_from_payload(payload: dict[str, Any]) -> ClothingLayers:
    """Map a provider dictionary onto the clothing-layers DTO."""
    return ClothingLayers.model_validate(
        {
            "base_layer": payload["base_layer"],
            "mid_layer": payload.get("mid_layer"),
            "outer_layer": payload.get("outer_layer"),
            "accessories": payload.get("accessories", []),
            "risk_level": payload["risk_level"],
            "utci_category": payload["utci_category"],
        }
    )

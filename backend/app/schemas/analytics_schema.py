"""HTTP models for partner analytics. Responses contain aggregates only."""

from datetime import date

from pydantic import BaseModel, ConfigDict, computed_field


class GarmentStatResponse(BaseModel):
    """One garment's count and share inside a slice."""

    garment: str
    category: str
    count: int
    percentage: float


class TimelinePointResponse(BaseModel):
    """Daily recommendation and feedback volume."""

    model_config = ConfigDict(from_attributes=True)

    day: date
    recommendations: int
    feedback: int

    @computed_field
    @property
    def recommendations_count(self) -> int:
        """Return the daily recommendation total under the chart field name."""
        return self.recommendations

    @computed_field
    @property
    def feedback_count(self) -> int:
        """Return the daily feedback total under the chart field name."""
        return self.feedback


class SentimentSliceResponse(BaseModel):
    """One thermal-rating share: too_cold, perfect, or too_warm."""

    rating: str
    count: int
    percentage: float


class TemperatureLayerBandResponse(BaseModel):
    """Layer groups recommended inside one temperature band."""

    bucket: str
    recommendation_count: int
    layers: list[GarmentStatResponse]


class GenderShareResponse(BaseModel):
    """Registered accounts in one wearer segment."""

    gender: str
    count: int
    percentage: float


class KpiSummaryResponse(BaseModel):
    """Overview figures for the selected window."""

    total_registered_users: int
    active_wearers: int
    total_recommendations: int
    thermal_satisfaction_rate: float
    most_frequent_garment: str | None
    most_frequent_garment_category: str | None
    most_frequent_garment_count: int
    timeline: list[TimelinePointResponse]
    sentiment_breakdown: list[SentimentSliceResponse]
    temperature_layer_breakdown: list[TemperatureLayerBandResponse]
    accessories_distribution: list[GarmentStatResponse]
    user_demographics_gender: list[GenderShareResponse]


class ClothingTrendResponse(BaseModel):
    """Garments grouped by city, temperature band, and wearer gender."""

    city: str
    bucket: str
    gender: str
    recommendation_count: int
    garments: list[GarmentStatResponse]


class TemperatureBucketResponse(BaseModel):
    """Garments grouped into one city and effective-temperature band."""

    city: str
    bucket: str
    recommendation_count: int
    garments: list[GarmentStatResponse]

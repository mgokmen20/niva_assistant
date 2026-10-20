"""Partner analytics routes.

Handlers read query parameters, call the analytics service, and map DTOs.
Aggregation stays in the service. Responses contain no wearer identifiers.
"""

import logging
from collections.abc import Awaitable, Iterator
from datetime import date
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.constants import (
    ANALYTICS_DEFAULT_DAYS,
    ANALYTICS_DISTRIBUTION_DAYS,
    ANALYTICS_MAX_DAYS,
)
from ...models.user import User
from ...schemas.analytics_schema import (
    ClothingTrendResponse,
    GarmentStatResponse,
    GenderShareResponse,
    KpiSummaryResponse,
    SentimentSliceResponse,
    TemperatureBucketResponse,
    TemperatureLayerBandResponse,
    TimelinePointResponse,
)
from ...services.analytics import (
    AnalyticsWindowError,
    build_clothing_trends_csv,
    get_clothing_trends,
    get_garment_distribution_by_city,
    get_kpi_summary,
    get_temperature_threshold_correlations,
)
from ..deps import get_db, require_partner_or_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])
_CSV_MEDIA_TYPE = "text/csv"
_CSV_FILENAME = "niva-clothing-trends.csv"
_ResultT = TypeVar("_ResultT")


async def _bounded(awaitable: Awaitable[_ResultT]) -> _ResultT:
    """Run an analytics query and map a bad window to 422."""
    try:
        return await awaitable
    except AnalyticsWindowError as exc:
        logger.warning("Analytics window was rejected.", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected dates are not valid.",
        ) from exc


@router.get("/overview", response_model=KpiSummaryResponse)
async def read_overview(
    days: int = Query(default=ANALYTICS_DEFAULT_DAYS, ge=1, le=ANALYTICS_MAX_DAYS),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    city: str | None = Query(default=None, max_length=120),
    gender: str | None = Query(default=None, max_length=16),
    _: User = Depends(require_partner_or_admin),
    db: AsyncSession = Depends(get_db),
) -> KpiSummaryResponse:
    """Return KPI totals and the daily volume for the selected window."""
    summary = await _bounded(get_kpi_summary(
        db,
        city=city,
        days=days,
        start_date=start_date,
        end_date=end_date,
        gender=gender,
    ))
    return KpiSummaryResponse(
        total_registered_users=summary.total_registered_users,
        active_wearers=summary.active_wearers,
        total_recommendations=summary.total_recommendations,
        thermal_satisfaction_rate=summary.thermal_satisfaction_rate,
        most_frequent_garment=summary.most_frequent_garment,
        most_frequent_garment_category=summary.most_frequent_garment_category,
        most_frequent_garment_count=summary.most_frequent_garment_count,
        timeline=[
            TimelinePointResponse(
                day=point.day,
                recommendations=point.recommendations,
                feedback=point.feedback,
            )
            for point in summary.timeline
        ],
        sentiment_breakdown=[
            SentimentSliceResponse(
                rating=item.rating,
                count=item.count,
                percentage=item.percentage,
            )
            for item in summary.sentiment_breakdown
        ],
        temperature_layer_breakdown=[
            TemperatureLayerBandResponse(
                bucket=band.bucket,
                recommendation_count=band.recommendation_count,
                layers=[
                    GarmentStatResponse(
                        garment=item.garment,
                        category=item.category,
                        count=item.count,
                        percentage=item.percentage,
                    )
                    for item in band.layers
                ],
            )
            for band in summary.temperature_layer_breakdown
        ],
        accessories_distribution=[
            GarmentStatResponse(
                garment=item.garment,
                category=item.category,
                count=item.count,
                percentage=item.percentage,
            )
            for item in summary.accessories_distribution
        ],
        user_demographics_gender=[
            GenderShareResponse(
                gender=item.gender,
                count=item.count,
                percentage=item.percentage,
            )
            for item in summary.user_demographics_gender
        ],
    )


@router.get("/trends", response_model=list[ClothingTrendResponse])
async def read_clothing_trends(
    days: int | None = Query(default=None, ge=1, le=ANALYTICS_MAX_DAYS),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    city: str | None = Query(default=None, max_length=120),
    gender: str | None = Query(default=None, max_length=16),
    _: User = Depends(require_partner_or_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ClothingTrendResponse]:
    """Return garment demand for the selected city, window, and gender."""
    trends = await _bounded(get_clothing_trends(
        db,
        city=city,
        days=days,
        start_date=start_date,
        end_date=end_date,
        gender=gender,
    ))
    return [
        ClothingTrendResponse(
            city=item.city,
            bucket=item.bucket,
            gender=item.gender,
            recommendation_count=item.recommendation_count,
            garments=[
                GarmentStatResponse(
                    garment=garment.garment,
                    category=garment.category,
                    count=garment.count,
                    percentage=garment.percentage,
                )
                for garment in item.garments
            ],
        )
        for item in trends
    ]


@router.get("/clothing-distribution", response_model=list[GarmentStatResponse])
async def read_clothing_distribution(
    city: str = Query(min_length=1, max_length=120),
    days: int = Query(default=ANALYTICS_DISTRIBUTION_DAYS, ge=1, le=ANALYTICS_MAX_DAYS),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: User = Depends(require_partner_or_admin),
    db: AsyncSession = Depends(get_db),
) -> list[GarmentStatResponse]:
    """Return garment counts and percentages for one city."""
    stats = await _bounded(get_garment_distribution_by_city(
        db,
        city=city,
        days=days,
        start_date=start_date,
        end_date=end_date,
    ))
    return [
        GarmentStatResponse(
            garment=item.garment,
            category=item.category,
            count=item.count,
            percentage=item.percentage,
        )
        for item in stats
    ]


@router.get("/temperature-correlations", response_model=list[TemperatureBucketResponse])
async def read_temperature_correlations(
    city: str | None = Query(default=None, max_length=120),
    days: int | None = Query(default=None, ge=1, le=ANALYTICS_MAX_DAYS),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: User = Depends(require_partner_or_admin),
    db: AsyncSession = Depends(get_db),
) -> list[TemperatureBucketResponse]:
    """Return garment mixes for each effective-temperature band."""
    buckets = await _bounded(get_temperature_threshold_correlations(
        db,
        city=city,
        days=days,
        start_date=start_date,
        end_date=end_date,
    ))
    return [
        TemperatureBucketResponse(
            city=bucket.city,
            bucket=bucket.bucket,
            recommendation_count=bucket.recommendation_count,
            garments=[
                GarmentStatResponse(
                    garment=item.garment,
                    category=item.category,
                    count=item.count,
                    percentage=item.percentage,
                )
                for item in bucket.garments
            ],
        )
        for bucket in buckets
    ]


@router.get("/export-csv")
async def export_clothing_trends_csv(
    days: int = Query(default=ANALYTICS_DISTRIBUTION_DAYS, ge=1, le=ANALYTICS_MAX_DAYS),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    city: str | None = Query(default=None, max_length=120),
    gender: str | None = Query(default=None, max_length=16),
    _: User = Depends(require_partner_or_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream anonymized garment counts as a CSV download."""
    content = await _bounded(build_clothing_trends_csv(
        db,
        city=city,
        days=days,
        start_date=start_date,
        end_date=end_date,
        gender=gender,
    ))
    return StreamingResponse(
        _csv_chunks(content),
        media_type=_CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{_CSV_FILENAME}"'},
    )


def _csv_chunks(content: str) -> Iterator[str]:
    """Yield the CSV body so the response can stream it."""
    yield content

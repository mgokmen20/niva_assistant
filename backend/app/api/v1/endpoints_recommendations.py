"""Recommendation and feedback routes.

Handlers parse the request, call a service, and map the DTO. Clothing
math and SQL stay in the service layer.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import WeatherAPIUnavailableError, WeatherServiceError
from ...core.security import mask_ip_address
from ...models.user import User
from ...services.analytics import segment_from_profile, temperature_bucket
from ...schemas.recommendation_schema import (
    FeedbackRequest,
    FeedbackResponse,
    RecommendationRequest,
    RecommendationResponse,
    clothing_layers_from_payload,
)
from ...services.calibration import calculate_user_thermal_offset, wearer_age_years
from ...services.feedback_service import FeedbackService
from ...services.llm_service import load_wearer_decision_context
from ...services.tts_service import normalize_language
from ...services.recommendation_log_service import RecommendationLogService
from ...services.recommendation_service import RecommendationService
from ..deps import (
    get_current_user_id,
    get_db,
    get_feedback_service,
    get_current_user_id,
    get_optional_db,
    get_recommendation_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
_log_service = RecommendationLogService()


def _recommendation_response(
    payload: dict[str, Any],
    recommendation_id: UUID | None,
) -> RecommendationResponse:
    """Map a service dictionary onto the public recommendation DTO."""
    meteorology = payload["meteorology"]
    return RecommendationResponse(
        recommendation_id=recommendation_id,
        effective_temperature=float(payload["effective_temperature_celsius"]),
        meteorology=meteorology,
        clothing_layers=clothing_layers_from_payload(payload),
        voice_summary=str(payload["voice_summary"]),
        personal_offset=float(payload.get("personal_offset") or 0.0),
    )


async def _store_recommendation(
    db: AsyncSession,
    *,
    city_name: str,
    client_ip_masked: str,
    payload: dict[str, Any],
    user_id: UUID,
) -> UUID | None:
    """Persist the shown recommendation when a session is open."""
    layers = clothing_layers_from_payload(payload).model_dump()
    effective = float(payload["effective_temperature_celsius"])
    try:
        stored_gender = await db.scalar(select(User.gender).where(User.id == user_id))
        entry = await _log_service.record(
            db,
            location_name=city_name,
            air_temperature=float(payload["meteorology"]["air_temperature"]),
            effective_temperature=effective,
            recommended_layers=layers,
            decision_engine_used=str(payload["provider"]),
            client_ip_masked=client_ip_masked,
            temperature_band=temperature_bucket(effective),
            user_id=user_id,
            gender=segment_from_profile(stored_gender if isinstance(stored_gender, str) else None),
        )
    except Exception:
        logger.warning("Recommendation log was not stored.")
        await db.rollback()
        return None
    return entry.id


@router.post("/current", response_model=RecommendationResponse)
async def create_current_recommendation(
    body: RecommendationRequest,
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
    db: AsyncSession | None = Depends(get_optional_db),
    lang: str = Query(default="en"),
) -> RecommendationResponse:
    """Return the clothing recommendation for a signed-in wearer.

    Guests are rejected before any clothing or voice work. ``mode`` selects
    a light, balanced, or warm outfit around the calibrated decision
    temperature. The served garments, wearer id, temperature band, and city
    are stored when a database session is available. The client address is
    stored only as an nDSG network prefix.
    """
    host = request.client.host if request.client is not None else None
    language = normalize_language(lang)
    personal_offset = 0.0
    age = 30
    wearer_context = None
    if db is not None:
        personal_offset = await calculate_user_thermal_offset(user_id, db)
        age = await wearer_age_years(user_id, db)
        wearer_context = await load_wearer_decision_context(user_id, db, personal_offset)
    try:
        payload = await recommendation_service.get_recommendation(
            latitude=body.latitude,
            longitude=body.longitude,
            age=age,
            city_name=body.city_name,
            first_name=body.first_name,
            personal_offset=personal_offset,
            outfit_preference=body.mode,
            language=language,
            wearer_context=wearer_context,
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

    recommendation_id: UUID | None = None
    if db is not None:
        masked_ip = mask_ip_address(host) or "unknown"
        recommendation_id = await _store_recommendation(
            db,
            city_name=body.city_name,
            client_ip_masked=masked_ip,
            payload=payload,
            user_id=user_id,
        )
    return _recommendation_response(payload, recommendation_id)


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_recommendation_feedback(
    body: FeedbackRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    feedback_service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    """Record a thermal rating and update the wearer's comfort offset."""
    try:
        summary = await feedback_service.process_user_feedback(
            db,
            user_id=user_id,
            recommendation_id=body.recommendation_id,
            rating=body.rating,
            followed=body.followed_recommendation,
        )
    except ValueError as exc:
        logger.warning("Recommendation feedback was rejected.", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The recommendation could not be updated.",
        ) from exc
    return FeedbackResponse.model_validate(summary)

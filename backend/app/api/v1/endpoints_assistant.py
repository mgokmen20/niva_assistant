"""Ask Niva dialog route.

The handler resolves a city, then asks the voice chat service for a
two-sentence reply and neural audio. Clothing math stays in the service.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import (
    GeocodingServiceError,
    GeocodingUnavailableError,
    WeatherAPIUnavailableError,
    WeatherServiceError,
)
from ...core.constants import ASSISTANT_ASK_RATE_LIMIT
from ...schemas.assistant_schema import AssistantAnswerResponse, AssistantQuestionRequest
from ...services.geocoding_service import GeocodingService
from ...services.llm_service import sanitize_prompt_text
from ...services.voice_chat import VoiceChatService
from ..deps import get_current_user_id, get_geocoding_service, get_optional_db, get_voice_chat_service
from ..limiter import limiter

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAnswerResponse)
@limiter.limit(ASSISTANT_ASK_RATE_LIMIT)
async def ask_niva(
    request: Request,
    body: AssistantQuestionRequest,
    user_id: UUID = Depends(get_current_user_id),
    chat_service: VoiceChatService = Depends(get_voice_chat_service),
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    db: AsyncSession | None = Depends(get_optional_db),
) -> AssistantAnswerResponse:
    """Answer a typed or spoken question in the requested language.

    The reply uses current weather, the hourly day parts, the outfit the
    cards would show, and the wearer's thermal profile. Audio is empty
    when speech synthesis cannot run.
    """
    try:
        matches = await geocoding_service.search(body.city)
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
    if not matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City was not found.")
    place = matches[0]
    try:
        payload = await chat_service.answer_in_language(
            question=sanitize_prompt_text(body.question),
            latitude=float(place["latitude"]),
            longitude=float(place["longitude"]),
            city_name=str(place["name"]),
            language=body.lang,
            user_id=user_id,
            db=db,
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
    return AssistantAnswerResponse.model_validate(payload)

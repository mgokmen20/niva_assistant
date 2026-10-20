"""Neural voice routes.

Handlers validate the sentence and stream MP3 bytes, or return a short
spoken answer. Synthesis and chat stay in the service layer.
"""

import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import (
    VoiceServiceError,
    VoiceUnavailableError,
    WeatherAPIUnavailableError,
    WeatherServiceError,
)
from ...schemas.voice_schema import SpeechRequest, VoiceAnswerResponse, VoiceQuestionRequest
from ...services.tts_service import voice_for_language
from ...services.voice import generate_speech_audio
from ...services.voice_chat import VoiceChatService
from ..deps import (
    get_current_user_id,
    get_optional_db,
    get_voice_chat_service,
)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/synthesize")
async def synthesize_speech(
    body: SpeechRequest,
    _: UUID = Depends(get_current_user_id),
) -> StreamingResponse:
    """Return neural MP3 audio for a signed-in wearer.

    Guests are rejected before synthesis. An unreachable voice service
    answers 503 so the client can use its local speech engine.
    """
    try:
        audio_bytes = await generate_speech_audio(body.text, voice=voice_for_language(body.language))
    except VoiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice synthesis is unavailable.",
        ) from exc
    except VoiceServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Voice synthesis failed.",
        ) from exc
    return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")


@router.post("/ask", response_model=VoiceAnswerResponse)
async def ask_voice_question(
    body: VoiceQuestionRequest,
    user_id: UUID = Depends(get_current_user_id),
    chat_service: VoiceChatService = Depends(get_voice_chat_service),
    db: AsyncSession | None = Depends(get_optional_db),
) -> VoiceAnswerResponse:
    """Answer a spoken question for a signed-in wearer.

    Guests are rejected before any model or speech call. The wearer id
    adds their name, gender, and thermal offset. Missing Cloudflare
    credentials, or a failed model call, use the deterministic weather
    reply instead.
    """
    try:
        payload = await chat_service.answer(
            question=body.question,
            latitude=body.latitude,
            longitude=body.longitude,
            city_name=body.city_name,
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
    return VoiceAnswerResponse.model_validate(payload)

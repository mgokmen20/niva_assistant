"""Request and response models for neural speech and spoken questions."""

from pydantic import BaseModel, Field, field_validator

from ..core.constants import SPEECH_TEXT_MAX_LENGTH, VOICE_QUESTION_MAX_LENGTH
from ..services.llm_service import sanitize_prompt_text


class SpeechRequest(BaseModel):
    """One sentence to speak aloud, in the wearer's active language."""

    text: str = Field(min_length=1, max_length=SPEECH_TEXT_MAX_LENGTH)
    language: str = "en"

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Reject blank text after surrounding whitespace is removed."""
        spoken = value.strip()
        if spoken == "":
            raise ValueError("Text must not be blank.")
        return spoken

    @field_validator("language")
    @classmethod
    def known_language(cls, value: str) -> str:
        """Keep ``en``, ``de``, or ``tr`` and drop a region tag."""
        base = value.strip().lower().replace("_", "-").split("-", 1)[0]
        if base in {"en", "de", "tr"}:
            return base
        return "en"


class VoiceQuestionRequest(BaseModel):
    """A spoken question plus the place it refers to."""

    question: str = Field(min_length=1, max_length=VOICE_QUESTION_MAX_LENGTH)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    city_name: str = Field(min_length=1, max_length=120)

    @field_validator("question", mode="before")
    @classmethod
    def guard_question(cls, value: object) -> object:
        """Drop prompt-injection markers before the length check."""
        if isinstance(value, str):
            return sanitize_prompt_text(value)
        return value

    @field_validator("question", "city_name")
    @classmethod
    def strip_place_text(cls, value: str) -> str:
        """Reject blank text after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text


class VoiceAnswerResponse(BaseModel):
    """Spoken reply, its language, and neural MP3 audio as base64."""

    answer_text: str
    language: str
    audio_base64: str

"""Request and response models for the Ask Niva dialog."""

from pydantic import BaseModel, Field, field_validator

from ..core.constants import VOICE_QUESTION_MAX_LENGTH


class AssistantQuestionRequest(BaseModel):
    """A typed or spoken question for one city and language."""

    question: str = Field(min_length=1, max_length=VOICE_QUESTION_MAX_LENGTH)
    city: str = Field(min_length=1, max_length=120)
    lang: str = "en"

    @field_validator("question", "city")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Reject blank text after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text

    @field_validator("lang")
    @classmethod
    def known_language(cls, value: str) -> str:
        """Keep ``en``, ``de``, or ``tr`` and drop a region tag."""
        base = value.strip().lower().replace("_", "-").split("-", 1)[0]
        if base in {"en", "de", "tr"}:
            return base
        return "en"


class AssistantAnswerResponse(BaseModel):
    """Conversational reply and its neural MP3 audio as base64."""

    answer_text: str
    language: str
    audio_base64: str

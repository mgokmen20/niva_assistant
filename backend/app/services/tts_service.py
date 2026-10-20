"""Pick the Edge neural voice that matches the wearer's active language.

English, Swiss German, and Turkish each have one voice. Callers pass a
language code; this module does not detect language from the sentence.
"""

from ..core.constants import (
    DEFAULT_NEURAL_VOICE,
    GERMAN_NEURAL_VOICE,
    PREFERRED_LANGUAGE_DE,
    PREFERRED_LANGUAGE_EN,
    PREFERRED_LANGUAGE_TR,
    TURKISH_NEURAL_VOICE,
)
from .voice import generate_speech_audio

_VOICES = {
    PREFERRED_LANGUAGE_TR: TURKISH_NEURAL_VOICE,
    PREFERRED_LANGUAGE_DE: GERMAN_NEURAL_VOICE,
    PREFERRED_LANGUAGE_EN: DEFAULT_NEURAL_VOICE,
}


def normalize_language(language: str) -> str:
    """Return ``en``, ``de``, or ``tr``. Unknown tags become English.

    Region tags such as ``de-CH`` keep the language and drop the region.
    """
    base = language.strip().lower().replace("_", "-").split("-", 1)[0]
    if base in _VOICES:
        return base
    return PREFERRED_LANGUAGE_EN


def voice_for_language(language: str) -> str:
    """Return the Edge voice name for ``language``."""
    return _VOICES[normalize_language(language)]


async def synthesize_for_language(text: str, language: str = PREFERRED_LANGUAGE_EN) -> bytes:
    """Return MP3 bytes spoken in the voice for ``language``.

    Args:
        text: Sentence to speak.
        language: ``en``, ``de``, ``tr``, or a regional tag such as ``de-CH``.

    Returns:
        MPEG audio bytes from Edge TTS.
    """
    return await generate_speech_audio(text, voice=voice_for_language(language))

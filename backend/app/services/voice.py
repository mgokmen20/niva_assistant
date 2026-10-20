"""Neural speech from Microsoft Edge TTS.

The service needs no API key. Callers receive MP3 bytes. Network failures
and empty audio become ``VoiceUnavailableError`` so the HTTP layer can
answer 503 and the browser can use its local voice.
"""

import edge_tts
from edge_tts.exceptions import EdgeTTSException, NoAudioReceived, SkewAdjustmentError

from ..core.constants import DEFAULT_NEURAL_VOICE
from ..core.exceptions import VoiceUnavailableError

_AUDIO_CHUNK = "audio"


def _network_error_types() -> tuple[type[BaseException], ...]:
    """Return exception types that mean the voice host could not be reached."""
    kinds: list[type[BaseException]] = [TimeoutError, OSError, ConnectionError]
    try:
        import aiohttp
    except ImportError:
        return tuple(kinds)
    kinds.append(aiohttp.ClientError)
    return tuple(kinds)


async def generate_speech_audio(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
    """Return MP3 bytes for ``text`` spoken by ``voice``.

    Audio chunks from ``edge_tts.Communicate`` are joined in order.
    Metadata chunks are ignored.

    Args:
        text: Sentence to speak. Blank text is rejected.
        voice: Edge neural voice name. Defaults to ``en-US-ChristopherNeural``.

    Returns:
        MPEG audio bytes.

    Raises:
        ValueError: ``text`` or ``voice`` is blank.
        VoiceUnavailableError: The voice service is unreachable or silent.
    """
    spoken = text.strip()
    selected_voice = voice.strip()
    if spoken == "":
        raise ValueError("Speech text must not be blank.")
    if selected_voice == "":
        raise ValueError("Voice name must not be blank.")

    communicate = edge_tts.Communicate(spoken, selected_voice)
    parts: list[bytes] = []
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") != _AUDIO_CHUNK:
                continue
            data = chunk.get("data")
            if isinstance(data, (bytes, bytearray)) and len(data) > 0:
                parts.append(bytes(data))
    except NoAudioReceived as exc:
        raise VoiceUnavailableError("Neural voice service returned no audio.") from exc
    except (SkewAdjustmentError, EdgeTTSException) as exc:
        raise VoiceUnavailableError("Neural voice service is unreachable.") from exc
    except _network_error_types() as exc:
        raise VoiceUnavailableError("Neural voice service is unreachable.") from exc

    audio = b"".join(parts)
    if audio == b"":
        raise VoiceUnavailableError("Neural voice service returned no audio.")
    return audio

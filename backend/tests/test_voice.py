"""Neural voice synthesis. The Edge service is mocked."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from edge_tts.exceptions import NoAudioReceived
from httpx import ASGITransport

from app.api.v1 import endpoints_voice
from app.core.constants import DEFAULT_NEURAL_VOICE, GERMAN_NEURAL_VOICE, TURKISH_NEURAL_VOICE
from app.core.exceptions import VoiceUnavailableError
from app.core.security import create_access_token
from app.main import app
from app.services import voice as voice_service


def _bearer(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Return a signed bearer header so synthesis is not treated as a guest."""
    monkeypatch.setenv("SECRET_KEY", "valid-long-signing-key-for-pytest-testing-environment-32")
    monkeypatch.setenv("ALGORITHM", "HS256")
    token = create_access_token({"sub": str(uuid4())})
    return {"Authorization": f"Bearer {token}"}


class _FakeCommunicate:
    """Stand-in that yields two audio chunks and one metadata chunk."""

    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """Yield the chunks a successful Edge stream would produce."""
        yield {"type": "audio", "data": b"ID3"}
        yield {"type": "WordBoundary", "offset": 0.0, "duration": 0.2, "text": "Hi"}
        yield {"type": "audio", "data": b"mp3"}


class _SilentCommunicate:
    """Stand-in that closes without audio."""

    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """Raise the same error Edge raises when no audio arrives."""
        raise NoAudioReceived("no audio")
        yield {"type": "audio", "data": b""}


@pytest.mark.asyncio
async def test_generate_speech_audio_joins_mpeg_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audio chunks are concatenated and metadata is dropped."""
    monkeypatch.setattr(voice_service.edge_tts, "Communicate", _FakeCommunicate)

    audio = await voice_service.generate_speech_audio("Hello there.")

    assert audio == b"ID3mp3"


@pytest.mark.asyncio
async def test_generate_speech_audio_reports_an_unreachable_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent Edge stream becomes an unavailable-voice error."""
    monkeypatch.setattr(voice_service.edge_tts, "Communicate", _SilentCommunicate)

    with pytest.raises(VoiceUnavailableError):
        await voice_service.generate_speech_audio("Hello there.")


@pytest.mark.asyncio
async def test_blank_speech_text_is_rejected() -> None:
    """Whitespace is not sent to the voice service."""
    with pytest.raises(ValueError):
        await voice_service.generate_speech_audio("   ")


@pytest.mark.asyncio
async def test_synthesize_endpoint_streams_mpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid sentence is returned as an MPEG stream."""

    async def fake_audio(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
        assert text == "Bring a jacket."
        assert voice == DEFAULT_NEURAL_VOICE
        return b"mp3-bytes"

    monkeypatch.setattr(endpoints_voice, "generate_speech_audio", fake_audio)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/voice/synthesize",
            headers=_bearer(monkeypatch),
            json={"text": "Bring a jacket."},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"mp3-bytes"


@pytest.mark.asyncio
async def test_synthesize_endpoint_returns_503_when_voice_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable voice service is a 503, not a server crash."""

    async def unavailable(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
        raise VoiceUnavailableError("down")

    monkeypatch.setattr(endpoints_voice, "generate_speech_audio", unavailable)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/voice/synthesize",
            headers=_bearer(monkeypatch),
            json={"text": "Bring a jacket."},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice synthesis is unavailable."


@pytest.mark.asyncio
async def test_synthesize_endpoint_rejects_blank_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank sentence is rejected before synthesis."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/voice/synthesize",
            headers=_bearer(monkeypatch),
            json={"text": "   "},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "voice_name"),
    [
        ("en", DEFAULT_NEURAL_VOICE),
        ("de", GERMAN_NEURAL_VOICE),
        ("tr", TURKISH_NEURAL_VOICE),
    ],
)
async def test_synthesize_endpoint_selects_the_language_voice(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    voice_name: str,
) -> None:
    """Edge TTS receives the neural voice for the requested language."""
    seen: list[str] = []

    async def fake_audio(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
        seen.append(voice)
        assert text == "Bring a jacket."
        return b"mp3-bytes"

    monkeypatch.setattr(endpoints_voice, "generate_speech_audio", fake_audio)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/voice/synthesize",
            headers=_bearer(monkeypatch),
            json={"text": "Bring a jacket.", "language": language},
        )

    assert response.status_code == 200
    assert seen == [voice_name]

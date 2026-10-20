"""Spoken questions. Cloudflare and Edge TTS are mocked."""

import base64
from typing import Any
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport

from app.api.deps import get_voice_chat_service
from app.core.config import Settings
from app.core.constants import DEFAULT_NEURAL_VOICE, GERMAN_NEURAL_VOICE, TURKISH_NEURAL_VOICE
from app.core.security import create_access_token
from app.main import app
from app.services.voice_chat import (
    VoiceChatService,
    _context_message,
    detect_reply_language,
    deterministic_answer,
    voice_for_language,
)


class _Recommendations:
    """Recommendation stand-in that records the wearer offset."""

    def __init__(self, rain: float = 60.0, wind: float = 1.0) -> None:
        self.calls: list[dict[str, Any]] = []
        self._rain = rain
        self._wind = wind

    async def get_recommendation(self, **kwargs: Any) -> dict[str, Any]:
        """Return a fixed outfit and remember the caller arguments."""
        self.calls.append(kwargs)
        return {
            "effective_temperature_celsius": 10.0,
            "meteorology": {
                "air_temperature": 11.0,
                "apparent_temperature": 10.0,
                "wind_speed": self._wind,
                "rain_probability": self._rain,
                "uv_index": 2.0,
            },
            "base_layer": {"id": "long_sleeve_base", "label": "Long-sleeve base layer"},
            "mid_layer": {"id": "fleece_mid_layer", "label": "Fleece mid-layer"},
            "outer_layer": {"id": "light_jacket", "label": "Light jacket"},
            "accessories": [{"id": "umbrella", "label": "Umbrella"}],
        }


def test_language_detection_covers_english_german_and_turkish() -> None:
    """Question language ignores Swiss place names."""
    assert detect_reply_language("Do I need an umbrella?") == "en"
    assert detect_reply_language("How is the weather today in Biel/Bienne", "Biel/Bienne") == "en"
    assert detect_reply_language("Ist es draussen kalt?") == "de"
    assert detect_reply_language("Wie ist das Wetter heute in Bern", "Bern") == "de"
    assert detect_reply_language("Hava çok rüzgarlı mı?") == "tr"
    assert detect_reply_language("Bugün ne giymeliyim") == "tr"


def test_context_lists_every_layer_and_the_signed_offset() -> None:
    """The model sees the same garments as the cards, including accessories."""
    context = _context_message(
        "How is the weather today",
        "Biel/Bienne",
        _outfit(),
        "Ada",
        "women",
        0.5,
    )
    assert "Required reply language: English" in context
    assert "Effective temperature C: 9.5" in context
    assert "The air temperature is 8°C, feeling like 9.5°C." in context
    assert "air temperature (8°C)" in context
    assert "effective feels-like temperature (9.5°C)" in context
    assert "Personal offset C: +0.5" in context
    assert "Base layer: Long-sleeve base layer" in context
    assert "Mid layer: Fleece mid-layer" in context
    assert "Outer layer: Light jacket" in context
    assert "Accessory: Warm hat" in context
    assert "Accessory: Umbrella" in context
    assert "Sky: clear skies" in context


def test_voice_map_selects_the_matching_neural_voice() -> None:
    """Each language uses the Edge voice named for that language."""
    assert voice_for_language("tr") == TURKISH_NEURAL_VOICE
    assert voice_for_language("de") == GERMAN_NEURAL_VOICE
    assert voice_for_language("en") == DEFAULT_NEURAL_VOICE


def test_deterministic_umbrella_answer_uses_the_question_language() -> None:
    """A German question keeps German and names every card garment."""
    recommendation = {
        "meteorology": {
            "air_temperature": 8.0,
            "apparent_temperature": 6.0,
            "rain_probability": 70.0,
            "wind_speed": 2.0,
        },
        "base_layer": {"id": "thermal_base_layer", "label": "Thermal base layer"},
        "mid_layer": None,
        "outer_layer": {"id": "waterproof_shell", "label": "Waterproof shell"},
        "accessories": [{"id": "umbrella", "label": "Umbrella"}],
    }
    answer = deterministic_answer("Brauche ich einen Regenschirm?", "Bern", recommendation)
    assert detect_reply_language(answer, "Bern") == "de"
    assert "Regenschirm" in answer
    assert "Thermo-Unterwäsche" in answer
    assert "Regenjacke" in answer


@pytest.mark.asyncio
async def test_missing_credentials_use_weather_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Cloudflare call is made when the account is not configured."""
    spoken: dict[str, str] = {}

    async def fake_audio(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
        spoken["text"] = text
        spoken["voice"] = voice
        return b"mp3"

    monkeypatch.setattr("app.services.voice_chat.generate_speech_audio", fake_audio)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request.url)

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    service = VoiceChatService(
        _Recommendations(),  # type: ignore[arg-type]
        settings=Settings(
            CLOUDFLARE_ACCOUNT_ID="",
            CLOUDFLARE_API_TOKEN="",
            SECRET_KEY="valid-long-signing-key-for-pytest-testing-environment-32",
            _env_file=None,
        ),
        http_client=client,
    )
    try:
        payload = await service.answer(
            question="Do I need an umbrella?",
            latitude=46.9,
            longitude=7.4,
            city_name="Bern",
            user_id=None,
            db=None,
        )
    finally:
        await client.aclose()

    assert payload["language"] == "en"
    assert "umbrella" in payload["answer_text"].lower()
    assert payload["audio_base64"] == base64.b64encode(b"mp3").decode("ascii")
    assert spoken["voice"] == DEFAULT_NEURAL_VOICE


@pytest.mark.asyncio
async def test_wrong_language_model_reply_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An English question stays English even when the model switches language."""
    spoken: dict[str, str] = {}
    prompts: list[str] = []

    async def fake_audio(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
        spoken["text"] = text
        spoken["voice"] = voice
        return b"mp3"

    monkeypatch.setattr("app.services.voice_chat.generate_speech_audio", fake_audio)

    def handler(request: httpx.Request) -> httpx.Response:
        prompts.append(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"success": True, "result": {"response": "Evet, şemsiye al."}},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = VoiceChatService(
        _Recommendations(),  # type: ignore[arg-type]
        settings=Settings(
            CLOUDFLARE_ACCOUNT_ID="acct",
            CLOUDFLARE_API_TOKEN="token",
            SECRET_KEY="valid-long-signing-key-for-pytest-testing-environment-32",
            _env_file=None,
        ),
        http_client=client,
    )
    try:
        payload = await service.answer(
            question="How is the weather today",
            latitude=47.1,
            longitude=7.2,
            city_name="Biel/Bienne",
            user_id=None,
            db=None,
        )
    finally:
        await client.aclose()

    assert payload["language"] == "en"
    assert spoken["voice"] == DEFAULT_NEURAL_VOICE
    assert "şemsiye" not in payload["answer_text"].lower()
    assert "umbrella" in payload["answer_text"].lower()
    assert "CRITICAL RULE - LANGUAGE MIRRORING" in prompts[0]
    assert "MANDATORY CLOTHING CONSISTENCY" in prompts[0]
    assert "Base layer:" in prompts[0]
    assert "Accessory: Umbrella" in prompts[0]


def _outfit() -> dict[str, Any]:
    """Return the card payload used by the language scenarios."""
    return {
        "effective_temperature_celsius": 9.5,
        "personal_offset": 0.5,
        "meteorology": {
            "air_temperature": 8.0,
            "apparent_temperature": 7.0,
            "wind_speed": 2.0,
            "rain_probability": 10.0,
            "uv_index": 1.0,
        },
        "base_layer": {"id": "long_sleeve_base", "label": "Long-sleeve base layer"},
        "mid_layer": {"id": "fleece_mid_layer", "label": "Fleece mid-layer"},
        "outer_layer": {"id": "light_jacket", "label": "Light jacket"},
        "accessories": [
            {"id": "warm_hat", "label": "Warm hat"},
            {"id": "umbrella", "label": "Umbrella"},
        ],
    }


class _FixedOutfit:
    """Recommendation stand-in with a warm hat and an umbrella."""

    async def get_recommendation(self, **kwargs: Any) -> dict[str, Any]:
        """Return the shared outfit and ignore caller coordinates."""
        return _outfit()


async def _spoken_answer(
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    city_name: str,
) -> tuple[dict[str, str], str]:
    """Ask without Cloudflare and return the payload plus the voice name."""
    spoken: dict[str, str] = {}

    async def fake_audio(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
        spoken["voice"] = voice
        return b"mp3"

    monkeypatch.setattr("app.services.voice_chat.generate_speech_audio", fake_audio)
    service = VoiceChatService(
        _FixedOutfit(),  # type: ignore[arg-type]
        settings=Settings(
            CLOUDFLARE_ACCOUNT_ID="",
            CLOUDFLARE_API_TOKEN="",
            SECRET_KEY="valid-long-signing-key-for-pytest-testing-environment-32",
            _env_file=None,
        ),
    )
    payload = await service.answer(
        question=question,
        latitude=47.1,
        longitude=7.2,
        city_name=city_name,
        user_id=None,
        db=None,
    )
    return payload, spoken["voice"]


@pytest.mark.asyncio
async def test_english_weather_question_uses_the_english_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An English question stays English beside a bilingual city name."""
    payload, voice = await _spoken_answer(
        monkeypatch,
        "How is the weather today",
        "Biel/Bienne",
    )
    assert payload["language"] == "en"
    assert voice == DEFAULT_NEURAL_VOICE
    assert "The air temperature is 8°C, feeling like 9.5°C" in payload["answer_text"]
    assert "Long-sleeve base layer" in payload["answer_text"]
    assert "Warm hat" in payload["answer_text"]
    assert "Umbrella" in payload["answer_text"]


@pytest.mark.asyncio
async def test_turkish_outfit_question_lists_every_card_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Turkish question names every layer and accessory in Turkish."""
    payload, voice = await _spoken_answer(
        monkeypatch,
        "Bugün ne giymeliyim",
        "Bern",
    )
    assert payload["language"] == "tr"
    assert voice == TURKISH_NEURAL_VOICE
    text = payload["answer_text"].casefold()
    assert "hava sıcaklığı 8°c, hissedilen ise 9.5°c" in text
    assert "uzun kollu içlik" in text
    assert "polar ara katman" in text
    assert "hafif ceket" in text
    assert "bere" in text
    assert "şemsiye" in text
    assert "temel layer" not in text


@pytest.mark.asyncio
async def test_german_weather_question_stays_german(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A German question is answered and spoken in German."""
    payload, voice = await _spoken_answer(
        monkeypatch,
        "Wie ist das Wetter heute",
        "Bern",
    )
    assert payload["language"] == "de"
    assert voice == GERMAN_NEURAL_VOICE
    assert "Die Lufttemperatur beträgt 8°C, gefühlt sind es 9.5°C" in payload["answer_text"]
    assert "Langarmshirt" in payload["answer_text"]
    assert "Mütze" in payload["answer_text"]
    assert "Regenschirm" in payload["answer_text"]


@pytest.mark.asyncio
async def test_unreachable_model_falls_back_to_weather_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A network failure still returns a deterministic sentence."""

    async def fake_audio(text: str, voice: str = DEFAULT_NEURAL_VOICE) -> bytes:
        return b"mp3"

    monkeypatch.setattr("app.services.voice_chat.generate_speech_audio", fake_audio)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = VoiceChatService(
        _Recommendations(rain=10.0, wind=8.0),  # type: ignore[arg-type]
        settings=Settings(
            CLOUDFLARE_ACCOUNT_ID="acct",
            CLOUDFLARE_API_TOKEN="token",
            SECRET_KEY="valid-long-signing-key-for-pytest-testing-environment-32",
            _env_file=None,
        ),
        http_client=client,
    )
    try:
        payload = await service.answer(
            question="Hava çok rüzgarlı mı?",
            latitude=46.9,
            longitude=7.4,
            city_name="Bern",
            user_id=None,
            db=None,
        )
    finally:
        await client.aclose()

    assert payload["language"] == "tr"
    assert "rüzgarlı" in payload["answer_text"]


@pytest.mark.asyncio
async def test_ask_endpoint_returns_text_language_and_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HTTP route maps the service payload onto the public JSON shape."""

    class _StubChat:
        async def answer(self, **kwargs: Any) -> dict[str, str]:
            assert kwargs["question"] == "Do I need an umbrella?"
            assert kwargs["city_name"] == "Bern"
            return {
                "answer_text": "Yes, bring an umbrella.",
                "language": "en",
                "audio_base64": "bXAz",
            }

    app.dependency_overrides[get_voice_chat_service] = lambda: _StubChat()
    monkeypatch.setenv("SECRET_KEY", "valid-long-signing-key-for-pytest-testing-environment-32")
    monkeypatch.setenv("ALGORITHM", "HS256")
    token = create_access_token({"sub": str(uuid4())})
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/voice/ask",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "question": "Do I need an umbrella?",
                    "latitude": 46.9,
                    "longitude": 7.4,
                    "city_name": "Bern",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "answer_text": "Yes, bring an umbrella.",
        "language": "en",
        "audio_base64": "bXAz",
    }

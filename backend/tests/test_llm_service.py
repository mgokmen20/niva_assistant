"""Outfit summaries. Cloudflare is mocked; the fallback stays deterministic."""

import json

import httpx
import pytest

from app.core.config import Settings
from app.core.constants import PREFERRED_LANGUAGE_DE, PREFERRED_LANGUAGE_EN, PREFERRED_LANGUAGE_TR
from app.services.llm_service import (
    SUMMARY_SYSTEM_PROMPTS,
    WearerDecisionContext,
    build_decision_context,
    compose_voice_summary,
    system_prompt_for,
)
from app.services.tts_service import synthesize_for_language, voice_for_language

_ACCOUNT = "acct_123"
_TOKEN = "llm-token-value"


def test_system_prompts_match_the_three_languages() -> None:
    """Each language keeps the required Workers AI system prompt."""
    assert system_prompt_for("tr-TR") == (
        "Sen Niva adında samimi ve pratik bir termal giyim asistanısın. "
        "Kullanıcıya seçilen şehir ve sıcaklık için önerilen kıyafet katmanlarını "
        "doğal, sıcak ve motive edici bir Türkçe ile 2 kısa cümlede özetle."
    )
    assert system_prompt_for(PREFERRED_LANGUAGE_DE) == SUMMARY_SYSTEM_PROMPTS[PREFERRED_LANGUAGE_DE]
    assert "ß" in SUMMARY_SYSTEM_PROMPTS[PREFERRED_LANGUAGE_DE]
    assert system_prompt_for("en-US") == SUMMARY_SYSTEM_PROMPTS[PREFERRED_LANGUAGE_EN]
    assert system_prompt_for("fr") == SUMMARY_SYSTEM_PROMPTS[PREFERRED_LANGUAGE_EN]


def test_decision_context_includes_offset_routine_and_feedback() -> None:
    """The model sees why the outfit changed, not only the garment names."""
    context = build_decision_context(
        language="tr",
        city_name="Bern",
        air_temperature_celsius=10.0,
        effective_temperature_celsius=8.5,
        wind_speed_mps=6.0,
        rain_probability_percent=20,
        recommendation={
            "base_layer": {"id": "long_sleeve_base", "label": "Long-sleeve base layer"},
            "mid_layer": {"id": "fleece_mid_layer", "label": "Fleece mid-layer"},
            "outer_layer": {"id": "light_jacket", "label": "Light jacket"},
            "accessories": [],
        },
        wearer=WearerDecisionContext(
            personal_offset_celsius=-1.5,
            environment_routine="mostly_outdoor",
            recent_ratings=("TOO_COLD", "PERFECT"),
        ),
    )
    assert "Personal temperature offset delta T C: -1.5" in context
    assert "Daily routine: mostly_outdoor" in context
    assert "Recent thermal feedback oldest first: TOO_COLD, PERFECT" in context
    assert "Outer layer: Light jacket" in context
    assert "Wind m/s: 6.0" in context


@pytest.mark.asyncio
async def test_compose_uses_the_model_reply_in_the_requested_language() -> None:
    """A Turkish Workers AI reply replaces the English script."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen["system"] = body["messages"][0]["content"]
        seen["user"] = body["messages"][1]["content"]
        assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": (
                        "10°C olmasına rağmen biraz rüzgar olduğu için hafif ceketini de almanı önerdim. "
                        "Konfor farkın bunu istedi."
                    )
                },
            },
            request=request,
        )

    settings = Settings(
        CLOUDFLARE_ACCOUNT_ID=_ACCOUNT,
        CLOUDFLARE_API_TOKEN=_TOKEN,
        _env_file=None,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        summary = await compose_voice_summary(
            language="tr",
            english_summary="Hello there! Bring a light jacket.",
            recommendation={"outer_layer": {"id": "light_jacket", "label": "Light jacket"}},
            city_name="Bern",
            air_temperature_celsius=10.0,
            effective_temperature_celsius=9.0,
            wind_speed_mps=6.0,
            rain_probability_percent=10,
            wearer=WearerDecisionContext(-1.5, "mostly_outdoor", ("TOO_COLD",)),
            settings=settings,
            http_client=client,
        )

    assert summary.startswith("10°C olmasına rağmen")
    assert seen["system"] == SUMMARY_SYSTEM_PROMPTS[PREFERRED_LANGUAGE_TR]
    assert "delta T C: -1.5" in str(seen["user"])
    assert _TOKEN not in json.dumps(seen)


@pytest.mark.asyncio
async def test_german_fallback_uses_swiss_spelling_without_credentials() -> None:
    """German stays on the local script and never uses ß when the model is absent."""
    summary = await compose_voice_summary(
        language="de",
        english_summary="Hello there!",
        recommendation={"outer_layer": {"id": "light_jacket", "label": "Light jacket"}},
        city_name="Bern",
        air_temperature_celsius=10.0,
        effective_temperature_celsius=9.0,
        wind_speed_mps=6.0,
        rain_probability_percent=0,
        wearer=WearerDecisionContext(-1.5, "mostly_outdoor", ()),
        settings=Settings(CLOUDFLARE_ACCOUNT_ID="", CLOUDFLARE_API_TOKEN="", _env_file=None),
    )
    assert "leichte Jacke" in summary
    assert "draussen" in summary
    assert "ß" not in summary
    assert not summary.startswith("Hello there!")


def test_voice_names_follow_the_active_language() -> None:
    """Each language maps to the Edge voice selected for Niva."""
    assert voice_for_language("en") == "en-US-ChristopherNeural"
    assert voice_for_language("de-CH") == "de-CH-JanNeural"
    assert voice_for_language("tr") == "tr-TR-EmelNeural"
    assert voice_for_language("fr") == "en-US-ChristopherNeural"


@pytest.mark.asyncio
async def test_synthesize_for_language_passes_the_selected_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthesis asks Edge for the voice that matches the language code."""
    seen: list[str] = []

    async def fake_audio(text: str, voice: str = "en-US-ChristopherNeural") -> bytes:
        seen.append(voice)
        assert text == "Merhaba"
        return b"mp3"

    monkeypatch.setattr("app.services.tts_service.generate_speech_audio", fake_audio)
    audio = await synthesize_for_language("Merhaba", "tr")
    assert audio == b"mp3"
    assert seen == ["tr-TR-EmelNeural"]

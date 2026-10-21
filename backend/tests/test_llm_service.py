"""Outfit summaries. Cloudflare is mocked; the fallback stays deterministic."""

import json

import httpx
import pytest

from app.core.config import Settings
from app.core.constants import PREFERRED_LANGUAGE_DE, PREFERRED_LANGUAGE_EN
from app.services.ai_service import summary_system_prompt
from app.services.llm_service import (
    WearerDecisionContext,
    build_decision_context,
    compose_voice_summary,
    system_prompt_for,
)
from app.services.tts_service import synthesize_for_language, voice_for_language

_ACCOUNT = "acct_123"
_TOKEN = "llm-token-value"


def test_system_prompts_match_the_three_languages() -> None:
    """The briefing prompt names the wearer, the place, and the exact outfit."""
    german = summary_system_prompt(
        language=PREFERRED_LANGUAGE_DE,
        weather_progression="Currently 10°C, reaching 18°C at noon.",
        selected_items="Hose, Pullover",
        user_name="Ada",
        location="Bern",
    )
    assert german.startswith("You are Niva, a premium digital wardrobe assistant.")
    assert "in German/DE." in german
    assert "User Name: Ada" in german
    assert "Location: Bern" in german
    assert "Weather Progression: Currently 10°C, reaching 18°C at noon." in german
    assert "Selected Outfit: Hose, Pullover" in german
    assert "indoor activities" in german
    assert "Grüezi Ada" in german
    assert "Hello Ada" in german
    assert "Do not guess the time of day." in german
    assert "Good morning" not in german
    assert "NOT 'Kot Pantolon'" in german
    assert "NOT 'Light Jacke'" in german
    assert "Die heutige Kleidungsempfehlung:" in german
    assert "Pants/Trousers (Pantolon)" in german
    assert "You do not choose clothes." in german
    assert "CRITICAL ITEM RULE" in german
    assert "locked, immutable data" in german
    assert "Şemsiye" in german
    assert "Regenschirm" in german
    assert "NEVER translate 'Umbrella' to 'Gözlük'" in german
    assert "Do not deviate from this concise structure." in german
    assert "full-zip fleece" not in german
    assert "Sabah" not in german
    assert system_prompt_for("en-US") == summary_system_prompt(
        language=PREFERRED_LANGUAGE_EN,
        weather_progression="Not provided.",
        selected_items="No clothing selected.",
    )
    assert "in English." in system_prompt_for("fr")


def test_decision_context_lists_facts_without_a_routine() -> None:
    """The model sees the outfit and the weather, not a reason to invent one."""
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
        user_name="Ada",
    )
    assert "User name: Ada" in context
    assert "Location: Bern" in context
    assert "Daily routine:" not in context
    assert "Personal temperature offset" not in context
    assert "thermal feedback" not in context
    assert "Selected outfit: Long-sleeve base layer, Fleece mid-layer, Light jacket" in context
    assert "Mid layer:" not in context
    assert "Outer layer:" not in context
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
    assert "in Turkish." in str(seen["system"])
    assert "Selected Outfit: Light jacket" in str(seen["system"])
    assert "Location: Bern" in str(seen["system"])
    assert "indoor activities" in str(seen["system"])
    assert "Mid layer:" not in str(seen["user"])
    assert "Daily routine:" not in str(seen["user"])
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

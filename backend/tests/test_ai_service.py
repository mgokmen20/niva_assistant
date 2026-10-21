"""Stylist JSON parsing. Cloudflare is mocked."""

import json

import httpx
import pytest

from app.core.config import Settings
from app.core.constants import STANDARD_CASUAL_PANTS_NAME, STANDARD_TSHIRT_NAME
from app.services.ai_service import parse_stylist_selection, select_outfit_items, stylist_system_prompt
from app.services.wardrobe_outfit import HybridPool, PoolItem, ROLE_BOTTOM, ROLE_TOP

_ACCOUNT = "acct_123"
_TOKEN = "llm-token-value"


def test_invalid_json_is_rejected() -> None:
    """Conversational text is a parse failure so the caller can pick at random."""
    allowed = {STANDARD_TSHIRT_NAME, STANDARD_CASUAL_PANTS_NAME}
    assert parse_stylist_selection("I would wear the sweater.", allowed) is None


def test_markdown_json_keeps_only_true_names() -> None:
    """A fenced object is parsed, and false or unknown keys are dropped."""
    allowed = {STANDARD_TSHIRT_NAME, STANDARD_CASUAL_PANTS_NAME}
    text = (
        "```json\n"
        '{"Standard T-Shirt": true, "Standard Casual Pants": false, "Mystery Hat": true}\n'
        "```"
    )
    assert parse_stylist_selection(text, allowed) == [STANDARD_TSHIRT_NAME]


def test_system_prompt_uses_the_decision_temperature() -> None:
    """The stylist prompt states the effective temperature and demands JSON."""
    prompt = stylist_system_prompt(8.5)
    assert prompt.startswith("You are a fashion stylist. The weather is 8.5°C.")
    assert "ONLY a valid JSON object" in prompt
    assert "No markdown, no conversational text." in prompt


@pytest.mark.asyncio
async def test_select_outfit_items_sends_the_pool_and_reads_json() -> None:
    """The combined pool is the user message, and true names come back."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen["system"] = body["messages"][0]["content"]
        seen["user"] = body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {"response": '{"Standard T-Shirt": true, "Standard Casual Pants": true}'},
            },
            request=request,
        )

    pool = HybridPool(
        items=(
            PoolItem(STANDARD_TSHIRT_NAME, ROLE_TOP, "standard_t_shirt", "BASE"),
            PoolItem(STANDARD_CASUAL_PANTS_NAME, ROLE_BOTTOM, "standard_casual_pants", "BASE"),
        ),
        outerwear_required=False,
    )
    settings = Settings(
        CLOUDFLARE_ACCOUNT_ID=_ACCOUNT,
        CLOUDFLARE_API_TOKEN=_TOKEN,
        _env_file=None,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        accepted = await select_outfit_items(
            pool,
            effective_temperature_celsius=19.0,
            settings=settings,
            http_client=client,
        )

    assert accepted == [STANDARD_TSHIRT_NAME, STANDARD_CASUAL_PANTS_NAME]
    assert "The weather is 19°C." in seen["system"]
    assert "Standard T-Shirt" in seen["user"]
    assert "Outerwear is needed: no." in seen["user"]


@pytest.mark.asyncio
async def test_select_outfit_items_returns_none_when_the_reply_is_not_json() -> None:
    """A non-JSON model reply is treated as a stylist failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": True, "result": {"response": "Wear the navy sweater today."}},
            request=request,
        )

    pool = HybridPool(
        items=(PoolItem(STANDARD_TSHIRT_NAME, ROLE_TOP, "standard_t_shirt", "BASE"),),
        outerwear_required=False,
    )
    settings = Settings(
        CLOUDFLARE_ACCOUNT_ID=_ACCOUNT,
        CLOUDFLARE_API_TOKEN=_TOKEN,
        _env_file=None,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with client:
        accepted = await select_outfit_items(
            pool,
            effective_temperature_celsius=19.0,
            settings=settings,
            http_client=client,
        )

    assert accepted is None

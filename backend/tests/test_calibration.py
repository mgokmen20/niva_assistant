"""Adaptive thermal offset from the latest wearer ratings."""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_optional_db, get_recommendation_service
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import app
from app.models import Base
from app.models.recommendation import FeedbackEntry, RecommendationLog
from app.models.user import User
from app.services.calibration import accumulate_thermal_offset, calculate_user_thermal_offset
from app.services.recommendation_service import RecommendationService
from app.services.weather_service import WeatherService

_FORECAST: dict[str, Any] = {
    "current": {
        "temperature_2m": 21.5,
        "apparent_temperature": 19.0,
        "relative_humidity_2m": 55,
        "wind_speed_10m": 18.0,
        "precipitation_probability": 40,
        "uv_index": 2.6,
        "time": "2026-10-19T09:15",
    }
}


def test_cold_and_warm_ratings_move_the_offset_in_opposite_directions() -> None:
    """Too cold lowers the decision temperature. Too warm raises it."""
    assert accumulate_thermal_offset(["TOO_COLD"]) == -0.5
    assert accumulate_thermal_offset(["TOO_WARM"]) == 0.5
    assert accumulate_thermal_offset(["TOO_COLD", "TOO_WARM"]) == 0.0


def test_perfect_rating_pulls_the_offset_toward_zero() -> None:
    """A perfect rating eases the running offset by a quarter degree."""
    assert accumulate_thermal_offset(["TOO_COLD", "PERFECT"]) == -0.25
    assert accumulate_thermal_offset(["TOO_WARM", "PERFECT"]) == 0.25
    assert accumulate_thermal_offset(["PERFECT"]) == 0.0


def test_offset_is_clamped_to_three_degrees() -> None:
    """Seven full steps cannot push the offset past the calibration bounds."""
    assert accumulate_thermal_offset(["TOO_COLD"] * 7) == -3.0
    assert accumulate_thermal_offset(["TOO_WARM"] * 7) == 3.0


def test_offset_starts_from_the_thermal_baseline() -> None:
    """Feedback moves the registration baseline, then stays inside the clamp."""
    assert accumulate_thermal_offset([], baseline=-1.5) == -1.5
    assert accumulate_thermal_offset(["TOO_COLD"], baseline=-1.5) == -2.0
    assert accumulate_thermal_offset(["TOO_WARM"], baseline=1.5) == 2.0
    assert accumulate_thermal_offset(["PERFECT"], baseline=-1.5) == -1.25
    assert accumulate_thermal_offset(["TOO_COLD"] * 7, baseline=-1.5) == -3.0


def test_empty_history_stays_neutral() -> None:
    """No ratings leave the outfit on the uncalibrated temperature."""
    assert accumulate_thermal_offset([]) == 0.0


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create a fresh SQLite schema for calibration queries."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield factory
    await engine.dispose()


async def _seed_ratings(
    session: AsyncSession,
    ratings_oldest_first: list[str],
) -> User:
    """Store one wearer and one feedback row per rating, oldest first."""
    wearer = User(
        id=uuid4(),
        email="ada@example.com",
        password_hash="hashed-password",
        first_name="Ada",
        last_name="Lovelace",
        birth_date=datetime(1990, 12, 10, tzinfo=timezone.utc).date(),
        gender="women",
    )
    session.add(wearer)
    await session.flush()
    origin = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for index, rating in enumerate(ratings_oldest_first):
        log = RecommendationLog(
            id=uuid4(),
            user_id=wearer.id,
            location_name="Bern",
            air_temperature=21.5,
            effective_temperature=19.0,
            recommended_layers={"base_layer": {"id": "light_t_shirt"}},
            decision_engine_used="rule_based",
            client_ip_masked="127.0.0.0",
            created_at=origin + timedelta(minutes=index),
        )
        session.add(log)
        await session.flush()
        session.add(
            FeedbackEntry(
                recommendation_id=log.id,
                user_id=wearer.id,
                thermal_rating=rating,
                followed_recommendation=True,
                applied_delta=0.0,
                created_at=origin + timedelta(minutes=index),
            )
        )
    await session.commit()
    return wearer


@pytest.mark.asyncio
async def test_query_uses_only_the_latest_ten_ratings(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ratings older than the window do not change the offset."""
    async with session_factory() as session:
        wearer = await _seed_ratings(
            session,
            ["TOO_WARM", "TOO_WARM", *["TOO_COLD"] * 4, *["PERFECT"] * 6],
        )
        offset = await calculate_user_thermal_offset(wearer.id, session)
    assert offset == -0.5


@pytest.mark.asyncio
async def test_wearer_without_feedback_stays_at_zero(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A saved account with no ratings is not shifted."""
    async with session_factory() as session:
        wearer = await _seed_ratings(session, [])
        offset = await calculate_user_thermal_offset(wearer.id, session)
    assert offset == 0.0


@pytest.mark.asyncio
async def test_authenticated_recommendation_applies_the_offset(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bearer token lowers the decision temperature after a cold rating."""
    monkeypatch.setenv("SECRET_KEY", "test-signing-key")
    monkeypatch.setenv("ALGORITHM", "HS256")
    async with session_factory() as session:
        wearer = await _seed_ratings(session, ["TOO_COLD"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_FORECAST, request=request)

    weather_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        CLOUDFLARE_ACCOUNT_ID="",
        CLOUDFLARE_API_TOKEN="",
        DATABASE_URL="",
        SECRET_KEY="test-signing-key",
        _env_file=None,
    )
    service = RecommendationService.create(
        WeatherService(client=weather_http),
        settings=settings,
    )

    async def override_recommendation_service() -> RecommendationService:
        return service

    async def override_optional_db() -> AsyncIterator[AsyncSession]:
        session = session_factory()
        try:
            yield session
            await session.commit()
        finally:
            await session.close()

    app.dependency_overrides[get_recommendation_service] = override_recommendation_service
    app.dependency_overrides[get_optional_db] = override_optional_db
    token = create_access_token({"sub": str(wearer.id)})
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/recommendations/current",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "latitude": 46.948,
                    "longitude": 7.4474,
                    "city_name": "Bern",
                    "mode": "auto",
                },
            )
    finally:
        app.dependency_overrides.clear()
        await weather_http.aclose()

    assert response.status_code == 200
    body = response.json()
    assert body["personal_offset"] == -0.5
    assert body["effective_temperature"] == 18.5

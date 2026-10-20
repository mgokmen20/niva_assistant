"""Analytics aggregates and partner access. Persistence uses in-memory SQLite."""

from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.constants import (
    ANALYTICS_BUCKET_11_TO_15,
    ANALYTICS_BUCKET_5_TO_10,
    ANALYTICS_BUCKET_ABOVE_15,
    ANALYTICS_BUCKET_BELOW_5,
)
from app.main import app
from app.models import Base
from app.models.recommendation import FeedbackEntry, RecommendationLog
from app.models.user import User
from app.services.analytics import (
    AnalyticsWindowError,
    get_garment_distribution_by_city,
    get_kpi_summary,
    get_temperature_threshold_correlations,
    purge_historical_logs,
    resolve_purge_window,
    temperature_bucket,
)

_NOW = datetime.now(timezone.utc)


def _layers(
    base: str,
    mid: str | None = None,
    accessory: str | None = None,
    outer: str | None = None,
    accessories: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build the outfit JSON stored on a recommendation log."""
    pieces = list(accessories)
    if accessory is not None:
        pieces.append(accessory)
    payload: dict[str, object] = {
        "base_layer": {"id": base, "label": base, "category": "BASE"},
        "mid_layer": None if mid is None else {"id": mid, "label": mid, "category": "MID"},
        "outer_layer": None if outer is None else {"id": outer, "label": outer, "category": "OUTER"},
        "accessories": [{"id": item, "label": item, "category": "ACCESSORY"} for item in pieces],
        "risk_level": "low",
        "utci_category": "COMFORT",
    }
    return payload


def _log(
    *,
    city: str,
    effective: float,
    layers: dict[str, object],
    user_id: object = None,
    created_at: datetime | None = None,
) -> RecommendationLog:
    """Build one recommendation row without writing it."""
    return RecommendationLog(
        id=uuid4(),
        user_id=user_id,
        location_name=city,
        air_temperature=effective,
        effective_temperature=effective,
        recommended_layers=layers,
        decision_engine_used="rules",
        client_ip_masked="unknown",
        created_at=created_at or _NOW,
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Yield a session on a fresh SQLite database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_kpi_math_counts_only_the_selected_window(session: AsyncSession) -> None:
    """Satisfaction, active wearers, and the top garment follow the window."""
    ada = User(
        email="ada@example.com",
        password_hash="hashed",
        first_name="Ada",
        last_name="Lovelace",
        birth_date=datetime(1990, 1, 1, tzinfo=timezone.utc).date(),
    )
    grace = User(
        email="grace@example.com",
        password_hash="hashed",
        first_name="Grace",
        last_name="Hopper",
        birth_date=datetime(1906, 12, 9, tzinfo=timezone.utc).date(),
    )
    session.add_all([ada, grace])
    await session.flush()
    recent_ada = _log(
        city="Bern",
        effective=4.0,
        layers=_layers("long_sleeve_base", "fleece_mid_layer"),
        user_id=ada.id,
        created_at=_NOW - timedelta(days=1),
    )
    recent_grace = _log(
        city="Bern",
        effective=12.0,
        layers=_layers("light_t_shirt", "fleece_mid_layer", "sunglasses"),
        user_id=grace.id,
        created_at=_NOW - timedelta(hours=2),
    )
    guest = _log(
        city="Bern",
        effective=16.0,
        layers=_layers("light_t_shirt"),
        created_at=_NOW - timedelta(hours=1),
    )
    stale = _log(
        city="Bern",
        effective=1.0,
        layers=_layers("thermal_base_layer"),
        user_id=ada.id,
        created_at=_NOW - timedelta(days=40),
    )
    other_city = _log(
        city="Zurich",
        effective=8.0,
        layers=_layers("long_sleeve_base"),
        user_id=ada.id,
    )
    session.add_all([recent_ada, recent_grace, guest, stale, other_city])
    await session.flush()
    session.add_all(
        [
            FeedbackEntry(
                recommendation_id=recent_ada.id,
                user_id=ada.id,
                thermal_rating="PERFECT",
                followed_recommendation=True,
                applied_delta=0.0,
                created_at=_NOW - timedelta(hours=3),
            ),
            FeedbackEntry(
                recommendation_id=recent_grace.id,
                user_id=grace.id,
                thermal_rating="TOO_COLD",
                followed_recommendation=True,
                applied_delta=0.5,
                created_at=_NOW - timedelta(hours=1),
            ),
            FeedbackEntry(
                recommendation_id=stale.id,
                user_id=ada.id,
                thermal_rating="PERFECT",
                followed_recommendation=True,
                applied_delta=0.0,
                created_at=_NOW - timedelta(days=40),
            ),
        ]
    )
    await session.commit()

    summary = await get_kpi_summary(session, city="Bern", days=7)

    assert summary.total_registered_users == 2
    assert summary.active_wearers == 2
    assert summary.total_recommendations == 3
    assert summary.thermal_satisfaction_rate == 50.0
    assert summary.most_frequent_garment == "fleece_mid_layer"
    assert summary.most_frequent_garment_category == "mid"
    assert summary.most_frequent_garment_count == 2
    assert len(summary.timeline) == 7
    assert sum(point.recommendations for point in summary.timeline) == 3
    assert sum(point.feedback for point in summary.timeline) == 2
    sentiment = {item.rating: item for item in summary.sentiment_breakdown}
    assert sentiment["perfect"].count == 1
    assert sentiment["perfect"].percentage == 50.0
    assert sentiment["too_cold"].count == 1
    assert sentiment["too_warm"].count == 0
    bands = {band.bucket: band for band in summary.temperature_layer_breakdown}
    assert bands[ANALYTICS_BUCKET_BELOW_5].recommendation_count == 1
    cold_fleece = next(item for item in bands[ANALYTICS_BUCKET_BELOW_5].layers if item.garment == "fleece")
    assert cold_fleece.count == 1
    accessories = {item.garment: item for item in summary.accessories_distribution}
    assert accessories["sunglasses"].count == 1
    assert accessories["sunglasses"].percentage == 100.0
    assert accessories["warm_hat"].count == 0


@pytest.mark.asyncio
async def test_layer_and_accessory_charts_group_the_tracked_garments(session: AsyncSession) -> None:
    """Winter coats, shells, fleece, and the four accessories land in chart groups."""
    session.add_all(
        [
            _log(
                city="Bern",
                effective=2.0,
                layers=_layers(
                    "thermal_base_layer",
                    "insulated_mid_layer",
                    outer="winter_coat",
                    accessories=("warm_hat", "scarf", "gloves"),
                ),
            ),
            _log(
                city="Bern",
                effective=8.0,
                layers=_layers("long_sleeve_base", "fleece_mid_layer", outer="light_jacket"),
            ),
            _log(
                city="Bern",
                effective=12.0,
                layers=_layers("long_sleeve_base", outer="wind_shell"),
            ),
            _log(
                city="Bern",
                effective=20.0,
                layers=_layers("light_t_shirt", accessory="sunglasses"),
            ),
        ]
    )
    await session.commit()

    summary = await get_kpi_summary(session, city="Bern", days=7)
    bands = {band.bucket: band for band in summary.temperature_layer_breakdown}

    def count(bucket: str, garment: str) -> int:
        return next(item.count for item in bands[bucket].layers if item.garment == garment)

    assert count(ANALYTICS_BUCKET_BELOW_5, "winter_coat") == 1
    assert count(ANALYTICS_BUCKET_BELOW_5, "fleece") == 1
    assert count(ANALYTICS_BUCKET_5_TO_10, "light_jacket") == 1
    assert count(ANALYTICS_BUCKET_11_TO_15, "light_jacket") == 1
    assert count(ANALYTICS_BUCKET_ABOVE_15, "t_shirt") == 1
    accessories = {item.garment: item for item in summary.accessories_distribution}
    assert accessories["warm_hat"].count == 1
    assert accessories["scarf"].percentage == 25.0
    assert accessories["gloves"].count == 1
    assert accessories["sunglasses"].percentage == 25.0


@pytest.mark.asyncio
async def test_distribution_percentages_and_temperature_buckets(session: AsyncSession) -> None:
    """Each piece's percentage uses the city's garment total, and bands stay closed."""
    session.add_all(
        [
            _log(city="Bern", effective=4.9, layers=_layers("thermal_base_layer", "fleece_mid_layer")),
            _log(city="Bern", effective=5.0, layers=_layers("long_sleeve_base")),
            _log(city="Bern", effective=10.0, layers=_layers("long_sleeve_base")),
            _log(city="Bern", effective=10.5, layers=_layers("light_t_shirt")),
            _log(city="Bern", effective=15.0, layers=_layers("light_t_shirt")),
            _log(city="Bern", effective=15.1, layers=_layers("light_t_shirt", accessory="sunglasses")),
            _log(city="Zurich", effective=4.0, layers=_layers("thermal_base_layer")),
        ]
    )
    await session.commit()

    distribution = await get_garment_distribution_by_city(session, city="bern", days=30)
    counts = {item.garment: item for item in distribution}
    assert counts["light_t_shirt"].count == 3
    assert counts["light_t_shirt"].percentage == 37.5
    assert counts["fleece_mid_layer"].category == "mid"
    assert counts["sunglasses"].category == "accessory"
    assert sum(item.count for item in distribution) == 8

    buckets = await get_temperature_threshold_correlations(session, city="Bern")
    by_name = {bucket.bucket: bucket.recommendation_count for bucket in buckets}
    assert by_name[ANALYTICS_BUCKET_BELOW_5] == 1
    assert by_name[ANALYTICS_BUCKET_5_TO_10] == 2
    assert by_name[ANALYTICS_BUCKET_11_TO_15] == 2
    assert by_name[ANALYTICS_BUCKET_ABOVE_15] == 1
    assert {bucket.city for bucket in buckets} == {"Bern"}
    everywhere = await get_temperature_threshold_correlations(session)
    assert {bucket.city for bucket in everywhere} == {"Bern", "Zurich"}
    assert temperature_bucket(10.0) == ANALYTICS_BUCKET_5_TO_10
    assert temperature_bucket(15.0) == ANALYTICS_BUCKET_11_TO_15


_WEARER: dict[str, str] = {
    "email": "wearer@example.com",
    "password": "correct-horse",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "birth_date": "1990-01-01",
}
_PARTNER: dict[str, str] = {
    "email": "partner@example.com",
    "password": "partner-horse-1",
    "first_name": "Pat",
    "last_name": "Ner",
    "birth_date": "1985-01-01",
}


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    """Serve the app with a fresh SQLite database."""
    monkeypatch.setenv("SECRET_KEY", "valid-long-signing-key-for-pytest-testing-environment-32")
    monkeypatch.setenv("ALGORITHM", "HS256")
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    app.state.session_factory = factory

    async def override_get_db() -> AsyncIterator[object]:
        db = factory()
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
    del app.state.session_factory
    await engine.dispose()


async def _token(http: httpx.AsyncClient, account: dict[str, str], role: str) -> str:
    """Register an account, assign ``role``, and return a bearer token."""
    created = await http.post("/api/v1/auth/register", json=account)
    assert created.status_code == 201
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as db:
        from sqlalchemy import select

        result = await db.execute(select(User).where(User.email == account["email"]))
        user = result.scalar_one()
        user.role = role
        db.add(
            _log(
                city="Bern",
                effective=4.0,
                layers=_layers("long_sleeve_base", "fleece_mid_layer"),
                user_id=user.id,
            )
        )
        await db.commit()
    signed_in = await http.post(
        "/api/v1/auth/login",
        data={"username": account["email"], "password": account["password"]},
    )
    assert signed_in.status_code == 200
    token = signed_in.json()["access_token"]
    assert isinstance(token, str)
    return token


@pytest.mark.asyncio
async def test_partner_can_read_analytics_and_user_is_forbidden(client: httpx.AsyncClient) -> None:
    """A partner receives the overview. A standard user receives 403."""
    user_token = await _token(client, _WEARER, "user")
    partner_token = await _token(client, _PARTNER, "partner")

    forbidden = await client.get(
        "/api/v1/analytics/overview",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert forbidden.status_code == 403

    overview = await client.get(
        "/api/v1/analytics/overview",
        headers={"Authorization": f"Bearer {partner_token}"},
        params={"city": "Bern", "days": 7},
    )
    assert overview.status_code == 200
    body = overview.json()
    assert body["total_recommendations"] == 2
    assert body["most_frequent_garment"] == "fleece_mid_layer"
    assert "email" not in overview.text
    assert len(body["timeline"]) == 7
    assert body["timeline"][0]["recommendations_count"] == body["timeline"][0]["recommendations"]
    assert body["timeline"][0]["feedback_count"] == body["timeline"][0]["feedback"]
    assert [item["rating"] for item in body["sentiment_breakdown"]] == [
        "too_cold",
        "perfect",
        "too_warm",
    ]
    assert len(body["temperature_layer_breakdown"]) == 4
    assert [item["garment"] for item in body["accessories_distribution"]] == [
        "warm_hat",
        "scarf",
        "gloves",
        "sunglasses",
    ]

    exported = await client.get(
        "/api/v1/analytics/export-csv",
        headers={"Authorization": f"Bearer {partner_token}"},
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "niva-clothing-trends.csv" in exported.headers["content-disposition"]
    first_line = exported.text.splitlines()[0]
    assert first_line == "city,gender,garment,category,count,percentage"
    assert "wearer@example.com" not in exported.text
    assert "fleece_mid_layer" in exported.text


@pytest.mark.asyncio
async def test_explicit_dates_replace_the_rolling_day_window(session: AsyncSession) -> None:
    """A start and end date keep only the logs inside that inclusive span."""
    session.add_all(
        [
            _log(
                city="Bern",
                effective=4.0,
                layers=_layers("thermal_base_layer"),
                created_at=datetime(2024, 1, 10, 8, tzinfo=timezone.utc),
            ),
            _log(
                city="Bern",
                effective=12.0,
                layers=_layers("light_t_shirt"),
                created_at=datetime(2024, 6, 1, 8, tzinfo=timezone.utc),
            ),
        ]
    )
    await session.commit()

    summary = await get_kpi_summary(
        session,
        city="Bern",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )

    assert summary.total_recommendations == 1
    assert summary.most_frequent_garment == "thermal_base_layer"
    assert len(summary.timeline) == 31
    assert summary.timeline[0].day == date(2024, 1, 1)
    assert summary.timeline[-1].day == date(2024, 1, 31)


@pytest.mark.asyncio
async def test_reversed_or_partial_dates_are_rejected(session: AsyncSession) -> None:
    """A custom range must be complete and ordered."""
    with pytest.raises(AnalyticsWindowError):
        await get_kpi_summary(session, start_date=date(2024, 2, 1), end_date=date(2024, 1, 1))
    with pytest.raises(AnalyticsWindowError):
        await get_garment_distribution_by_city(session, city="Bern", start_date=date(2024, 1, 1))


@pytest.mark.asyncio
async def test_purge_keeps_accounts_and_rows_outside_the_interval(session: AsyncSession) -> None:
    """Old logs and their feedback go away. Newer rows and the wearer stay."""
    ada = User(
        email="ada@example.com",
        password_hash="hashed",
        first_name="Ada",
        last_name="Lovelace",
        birth_date=date(1990, 1, 1),
    )
    session.add(ada)
    await session.flush()
    old = _log(
        city="Bern",
        effective=4.0,
        layers=_layers("thermal_base_layer"),
        user_id=ada.id,
        created_at=datetime(2020, 1, 15, 12, tzinfo=timezone.utc),
    )
    recent = _log(
        city="Bern",
        effective=12.0,
        layers=_layers("light_t_shirt"),
        user_id=ada.id,
        created_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
    )
    session.add_all([old, recent])
    await session.flush()
    session.add_all(
        [
            FeedbackEntry(
                recommendation_id=old.id,
                user_id=ada.id,
                thermal_rating="PERFECT",
                followed_recommendation=True,
                applied_delta=0.0,
                created_at=datetime(2020, 1, 16, 12, tzinfo=timezone.utc),
            ),
            FeedbackEntry(
                recommendation_id=recent.id,
                user_id=ada.id,
                thermal_rating="TOO_WARM",
                followed_recommendation=True,
                applied_delta=-0.5,
                created_at=datetime(2026, 10, 1, 13, tzinfo=timezone.utc),
            ),
        ]
    )
    await session.commit()

    window = resolve_purge_window(before_date=date(2024, 1, 1), start_date=None, end_date=None)
    removed = await purge_historical_logs(session, window, export_first=True)
    await session.commit()

    assert removed.recommendations == 1
    assert removed.feedback == 1
    assert removed.total == 2
    remaining_logs = (
        await session.execute(select(RecommendationLog.id).where(RecommendationLog.id == recent.id))
    ).scalar_one()
    assert remaining_logs == recent.id
    remaining_feedback = await session.scalar(select(func.count()).select_from(FeedbackEntry))
    assert remaining_feedback == 1
    assert await session.scalar(select(func.count()).select_from(User)) == 1

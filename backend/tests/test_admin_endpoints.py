"""Admin RBAC routes. Persistence uses in-memory SQLite."""

from collections.abc import AsyncIterator
from datetime import date, datetime, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, require_partner_or_admin
from app.main import app
from app.models import Base
from app.models.recommendation import FeedbackEntry, RecommendationLog
from app.models.user import User
from app.services.admin_service import seed_staff_accounts

_USER: dict[str, str] = {
    "email": "wearer@example.com",
    "password": "correct-horse",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "birth_date": "1990-01-01",
}
_ADMIN: dict[str, str] = {
    "email": "admin@example.com",
    "password": "admin-horse-1",
    "first_name": "Grace",
    "last_name": "Hopper",
    "birth_date": "1906-12-09",
}


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    """Serve the app with a fresh SQLite database and a session factory."""
    monkeypatch.setenv("SECRET_KEY", "test-signing-key")
    monkeypatch.setenv("ALGORITHM", "HS256")
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    app.state.session_factory = session_factory

    async def override_get_db() -> AsyncIterator[object]:
        session = session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
    del app.state.session_factory
    await engine.dispose()


async def _register(http: httpx.AsyncClient, account: dict[str, str]) -> str:
    """Register an account and return its id."""
    created = await http.post("/api/v1/auth/register", json=account)
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert isinstance(user_id, str)
    return user_id


async def _login(http: httpx.AsyncClient, account: dict[str, str], **headers: str) -> str:
    """Return a bearer token for ``account``."""
    signed_in = await http.post(
        "/api/v1/auth/login",
        data={"username": account["email"], "password": account["password"]},
        headers=headers,
    )
    assert signed_in.status_code == 200
    token = signed_in.json()["access_token"]
    assert isinstance(token, str)
    return token


async def _set_role(email: str, role: str) -> None:
    """Assign ``role`` through the test database, not the admin API."""
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.role = role
        await session.commit()


def _auth(token: str) -> dict[str, str]:
    """Build a bearer header."""
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_standard_user_cannot_list_accounts(client: httpx.AsyncClient) -> None:
    """A wearer with the user role receives 403."""
    await _register(client, _USER)
    token = await _login(client, _USER)

    response = await client.get("/api/v1/admin/users", headers=_auth(token))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_partner_cannot_list_accounts(client: httpx.AsyncClient) -> None:
    """Partner access is not enough for admin user management."""
    await _register(client, _USER)
    await _set_role(_USER["email"], "partner")
    token = await _login(client, _USER)

    response = await client.get("/api/v1/admin/users", headers=_auth(token))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_lists_changes_role_and_resets_password(client: httpx.AsyncClient) -> None:
    """An admin can list accounts, change a role, and replace a password."""
    wearer_id = await _register(client, _USER)
    await _register(client, _ADMIN)
    await _set_role(_ADMIN["email"], "admin")
    admin_token = await _login(
        client,
        _ADMIN,
        **{"X-Forwarded-For": "203.0.113.45"},
    )

    listed = await client.get("/api/v1/admin/users", headers=_auth(admin_token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert "password" not in listed.text
    emails = {item["email"] for item in body["items"]}
    assert emails == {_USER["email"], _ADMIN["email"]}
    admin_row = next(item for item in body["items"] if item["email"] == _ADMIN["email"])
    assert admin_row["role"] == "admin"
    assert admin_row["is_active"] is True
    assert admin_row["last_login_ip"] == "203.0.113.0"
    assert admin_row["last_login_at"] is not None
    assert "baseline_offset" in admin_row
    assert "created_at" in admin_row

    changed = await client.put(
        f"/api/v1/admin/users/{wearer_id}",
        headers=_auth(admin_token),
        json={"role": "partner", "thermal_preference": "warm_sensitive", "phone_number": "+41 79 111 11 11"},
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "partner"
    assert changed.json()["baseline_offset"] == 1.5
    assert changed.json()["phone_number"] == "+41 79 111 11 11"

    reset = await client.post(
        f"/api/v1/admin/users/{wearer_id}/reset-password",
        headers=_auth(admin_token),
        json={"new_password": "temporary-pass-1"},
    )
    assert reset.status_code == 204

    old_login = await client.post(
        "/api/v1/auth/login",
        data={"username": _USER["email"], "password": _USER["password"]},
    )
    new_login = await client.post(
        "/api/v1/auth/login",
        data={"username": _USER["email"], "password": "temporary-pass-1"},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_admin_soft_delete_blocks_login(client: httpx.AsyncClient) -> None:
    """Deleting an account marks it inactive and rejects the next login."""
    wearer_id = await _register(client, _USER)
    await _register(client, _ADMIN)
    await _set_role(_ADMIN["email"], "admin")
    admin_token = await _login(client, _ADMIN)

    deleted = await client.delete(f"/api/v1/admin/users/{wearer_id}", headers=_auth(admin_token))
    assert deleted.status_code == 204

    signed_in = await client.post(
        "/api/v1/auth/login",
        data={"username": _USER["email"], "password": _USER["password"]},
    )
    assert signed_in.status_code == 403

    listed = await client.get(
        "/api/v1/admin/users",
        headers=_auth(admin_token),
        params={"is_active": False, "search": "Ada"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["is_active"] is False


@pytest.mark.asyncio
async def test_seed_staff_creates_admin_and_partner(client: httpx.AsyncClient) -> None:
    """The seed helper stores one admin and one partner."""
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as session:
        admin, partner = await seed_staff_accounts(
            session,
            admin_email="seed-admin@example.com",
            admin_password="seed-admin-pass",
            partner_email="seed-partner@example.com",
            partner_password="seed-partner-pass",
        )
        await session.commit()
        assert admin.role == "admin"
        assert partner.role == "partner"

    admin_token = await _login(
        client,
        {
            "email": "seed-admin@example.com",
            "password": "seed-admin-pass",
            "first_name": "Niva",
            "last_name": "Admin",
            "birth_date": "1990-01-01",
        },
    )
    listed = await client.get("/api/v1/admin/users", headers=_auth(admin_token))
    assert listed.status_code == 200
    roles = {item["email"]: item["role"] for item in listed.json()["items"]}
    assert roles["seed-admin@example.com"] == "admin"
    assert roles["seed-partner@example.com"] == "partner"


@pytest.mark.asyncio
async def test_partner_or_admin_dependency_rejects_a_standard_user() -> None:
    """The reusable check allows partner and admin, and rejects user."""
    wearer = User(
        email="role-check@example.com",
        password_hash="not-used",
        first_name="Role",
        last_name="Check",
        birth_date=date(1990, 1, 1),
        role="user",
    )
    with pytest.raises(HTTPException) as caught:
        await require_partner_or_admin(wearer)
    assert caught.value.status_code == 403

    wearer.role = "partner"
    allowed = await require_partner_or_admin(wearer)
    assert allowed.role == "partner"


@pytest.mark.asyncio
async def test_admin_purge_removes_the_interval_and_partner_is_forbidden(
    client: httpx.AsyncClient,
) -> None:
    """An admin can preview, archive, and delete one span. A partner cannot."""
    await _register(client, _USER)
    await _register(client, _ADMIN)
    await _set_role(_ADMIN["email"], "admin")
    await _set_role(_USER["email"], "partner")
    admin_token = await _login(client, _ADMIN)
    partner_token = await _login(client, _USER)
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as session:
        owner = (await session.execute(select(User).where(User.email == _USER["email"]))).scalar_one()
        old = RecommendationLog(
            user_id=owner.id,
            location_name="Bern",
            air_temperature=4.0,
            effective_temperature=4.0,
            recommended_layers={"base_layer": {"id": "thermal_base_layer"}},
            decision_engine_used="rules",
            client_ip_masked="unknown",
            created_at=datetime(2020, 1, 15, 12, tzinfo=timezone.utc),
        )
        recent = RecommendationLog(
            user_id=owner.id,
            location_name="Bern",
            air_temperature=12.0,
            effective_temperature=12.0,
            recommended_layers={"base_layer": {"id": "light_t_shirt"}},
            decision_engine_used="rules",
            client_ip_masked="unknown",
            created_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
        )
        session.add_all([old, recent])
        await session.flush()
        session.add(
            FeedbackEntry(
                recommendation_id=old.id,
                user_id=owner.id,
                thermal_rating="PERFECT",
                followed_recommendation=True,
                applied_delta=0.0,
                created_at=datetime(2020, 1, 16, 12, tzinfo=timezone.utc),
            )
        )
        await session.commit()

    params = {"start_date": "2020-01-01", "end_date": "2020-01-31"}
    forbidden = await client.post(
        "/api/v1/admin/maintenance/purge-logs",
        headers=_auth(partner_token),
        json={**params, "export_first": True},
    )
    assert forbidden.status_code == 403

    preview = await client.get(
        "/api/v1/admin/maintenance/purge-preview",
        headers=_auth(admin_token),
        params=params,
    )
    assert preview.status_code == 200
    assert preview.json()["matching_count"] == 2

    archive = await client.get(
        "/api/v1/admin/maintenance/purge-archive",
        headers=_auth(admin_token),
        params=params,
    )
    assert archive.status_code == 200
    assert "niva-log-archive.csv" in archive.headers["content-disposition"]
    assert "thermal_base_layer" in archive.text
    assert _USER["email"] not in archive.text

    purged = await client.post(
        "/api/v1/admin/maintenance/purge-logs",
        headers=_auth(admin_token),
        json={**params, "export_first": True},
    )
    assert purged.status_code == 200
    assert purged.json()["purged_count"] == 2
    assert purged.json()["purged_recommendations"] == 1

    empty = await client.post(
        "/api/v1/admin/maintenance/purge-logs",
        headers=_auth(admin_token),
        json={"export_first": False},
    )
    assert empty.status_code == 422

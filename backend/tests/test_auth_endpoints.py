"""Auth route tests. Persistence uses in-memory SQLite, not a live server."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from jose import jwt
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app, lifespan
from app.models import Base

_SIGNING_KEY = "test-signing-key"
_ACCOUNT: dict[str, str] = {
    "email": "wearer@example.com",
    "password": "correct-horse",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "birth_date": "1990-12-10",
}


@pytest_asyncio.fixture
async def auth_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    """Serve the app with a fresh SQLite database and a known signing key."""
    monkeypatch.setenv("SECRET_KEY", _SIGNING_KEY)
    monkeypatch.setenv("ALGORITHM", "HS256")
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_lifespan_creates_user_and_recommendation_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup creates every ORM table without connecting to PostgreSQL."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr("app.main.get_engine", lambda: engine)

    async with lifespan(app):
        assert app.state.database_ready is True

    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )
    assert {
        "users",
        "user_locations",
        "recommendation_logs",
        "feedback_entries",
    } <= table_names
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_returns_profile_without_password(
    auth_client: httpx.AsyncClient,
) -> None:
    """A new account is stored and the response omits the password."""
    response = await auth_client.post("/api/v1/auth/register", json=_ACCOUNT)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "email",
        "first_name",
        "last_name",
        "birth_date",
        "role",
        "gender",
    }
    assert body["gender"] == "neutral"
    assert body["email"] == _ACCOUNT["email"]
    assert body["first_name"] == "Ada"
    assert body["role"] == "user"
    assert "password" not in response.text
    assert "password_hash" not in response.text


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(auth_client: httpx.AsyncClient) -> None:
    """A second registration with the same email returns 409."""
    first = await auth_client.post("/api/v1/auth/register", json=_ACCOUNT)
    assert first.status_code == 201

    duplicate = await auth_client.post("/api/v1/auth/register", json=_ACCOUNT)

    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_jwt(
    auth_client: httpx.AsyncClient,
) -> None:
    """OAuth2 form login returns a bearer token for the registered email."""
    created = await auth_client.post("/api/v1/auth/register", json=_ACCOUNT)
    assert created.status_code == 201
    user_id = created.json()["id"]

    form_login = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": _ACCOUNT["email"], "password": _ACCOUNT["password"]},
    )

    assert form_login.status_code == 200
    body = form_login.json()
    assert body["token_type"] == "bearer"
    claims = jwt.decode(body["access_token"], _SIGNING_KEY, algorithms=["HS256"])
    assert claims["sub"] == user_id


@pytest.mark.asyncio
async def test_remember_me_extends_the_token(auth_client: httpx.AsyncClient) -> None:
    """A remembered login stays valid for about 30 days."""
    from datetime import datetime, timedelta, timezone

    from app.core.constants import REMEMBER_ME_EXPIRE_DAYS

    created = await auth_client.post("/api/v1/auth/register", json=_ACCOUNT)
    assert created.status_code == 201
    remembered = await auth_client.post(
        "/api/v1/auth/login",
        data={
            "username": _ACCOUNT["email"],
            "password": _ACCOUNT["password"],
            "remember_me": "true",
        },
    )
    assert remembered.status_code == 200
    claims = jwt.decode(remembered.json()["access_token"], _SIGNING_KEY, algorithms=["HS256"])
    expires = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    remaining = expires - datetime.now(timezone.utc)
    assert remaining > timedelta(days=REMEMBER_ME_EXPIRE_DAYS - 1)


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials(auth_client: httpx.AsyncClient) -> None:
    """A wrong password and an unknown email both return 401."""
    created = await auth_client.post("/api/v1/auth/register", json=_ACCOUNT)
    assert created.status_code == 201

    wrong_password = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": _ACCOUNT["email"], "password": "not-the-password"},
    )
    unknown_email = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": "missing@example.com", "password": _ACCOUNT["password"]},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == "Invalid credentials"
    assert unknown_email.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_register_saves_gender_and_me_returns_profile(
    auth_client: httpx.AsyncClient,
) -> None:
    """Registration stores gender, and the bearer profile returns it."""
    account = {**_ACCOUNT, "email": "profile@example.com", "gender": "women"}
    created = await auth_client.post("/api/v1/auth/register", json=account)
    assert created.status_code == 201
    assert created.json()["gender"] == "women"

    form_login = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": account["email"], "password": account["password"]},
    )
    token = form_login.json()["access_token"]
    profile = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert profile.status_code == 200
    body = profile.json()
    assert body["id"] == created.json()["id"]
    assert body["gender"] == "women"
    assert "password" not in body

"""Profile routes. Persistence uses in-memory SQLite."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import Base

_ACCOUNT: dict[str, object] = {
    "email": "ada@example.com",
    "password": "correct-horse",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "birth_date": "1990-01-01",
    "gender": "women",
    "phone_number": "+41 79 000 00 00",
    "thermal_preference": "cold_sensitive",
    "environment_routine": "mostly_outdoor",
}


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    """Serve the app with a fresh SQLite database."""
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
    await engine.dispose()


async def _token(http: httpx.AsyncClient) -> str:
    """Register the sample wearer and return an access token."""
    created = await http.post("/api/v1/auth/register", json=_ACCOUNT)
    assert created.status_code == 201
    signed_in = await http.post(
        "/api/v1/auth/login",
        data={"username": "ada@example.com", "password": "correct-horse"},
    )
    assert signed_in.status_code == 200
    token = signed_in.json()["access_token"]
    assert isinstance(token, str)
    return token


@pytest.mark.asyncio
async def test_profile_returns_baseline_and_active_offset(client: httpx.AsyncClient) -> None:
    """A cold-sensitive account starts at -1.5 °C before any feedback."""
    token = await _token(client)
    response = await client.get(
        "/api/v1/profile/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["thermal_preference"] == "cold_sensitive"
    assert body["environment_routine"] == "mostly_outdoor"
    assert body["phone_number"] == "+41 79 000 00 00"
    assert body["baseline_offset"] == -1.5
    assert body["active_offset"] == -1.5
    assert body["preferred_language"] == "en"
    assert "password" not in response.text


@pytest.mark.asyncio
async def test_profile_update_changes_baseline(client: httpx.AsyncClient) -> None:
    """Switching to warm-sensitive moves the baseline to +1.5 °C."""
    token = await _token(client)
    response = await client.put(
        "/api/v1/profile/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "Ada",
            "last_name": "Byron",
            "email": "ada.byron@example.com",
            "phone_number": "",
            "thermal_preference": "warm_sensitive",
            "environment_routine": "mostly_indoor",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["last_name"] == "Byron"
    assert body["email"] == "ada.byron@example.com"
    assert body["phone_number"] is None
    assert body["baseline_offset"] == 1.5
    assert body["active_offset"] == 1.5
    assert body["gender"] == "women"
    assert body["birth_date"] == "1990-01-01"


@pytest.mark.asyncio
async def test_profile_update_can_change_gender_and_birth_date(client: httpx.AsyncClient) -> None:
    """Gender and birth date are editable with the thermal identity."""
    token = await _token(client)
    response = await client.put(
        "/api/v1/profile/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "phone_number": "+41 79 000 00 00",
            "thermal_preference": "cold_sensitive",
            "environment_routine": "mostly_outdoor",
            "gender": "men",
            "birth_date": "1985-06-15",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gender"] == "men"
    assert body["birth_date"] == "1985-06-15"


@pytest.mark.asyncio
async def test_profile_persists_preferred_language(client: httpx.AsyncClient) -> None:
    """PUT stores en, de, or tr and rejects any other code."""
    token = await _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    updated = await client.put(
        "/api/v1/profile/me",
        headers=headers,
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "phone_number": "+41 79 000 00 00",
            "thermal_preference": "cold_sensitive",
            "environment_routine": "mostly_outdoor",
            "preferred_language": "de",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["preferred_language"] == "de"

    again = await client.get("/api/v1/profile/me", headers=headers)
    assert again.status_code == 200
    assert again.json()["preferred_language"] == "de"

    rejected = await client.put(
        "/api/v1/profile/me",
        headers=headers,
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "phone_number": "+41 79 000 00 00",
            "thermal_preference": "cold_sensitive",
            "environment_routine": "mostly_outdoor",
            "preferred_language": "fr",
        },
    )
    assert rejected.status_code == 422
    unchanged = await client.get("/api/v1/profile/me", headers=headers)
    assert unchanged.json()["preferred_language"] == "de"


@pytest.mark.asyncio
async def test_change_password_rejects_the_current_password(client: httpx.AsyncClient) -> None:
    """A wrong current password does not replace the hash."""
    token = await _token(client)
    response = await client.post(
        "/api/v1/profile/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "wrong-password", "new_password": "new-password-1"},
    )
    assert response.status_code == 400

    signed_in = await client.post(
        "/api/v1/auth/login",
        data={"username": "ada@example.com", "password": "correct-horse"},
    )
    assert signed_in.status_code == 200


@pytest.mark.asyncio
async def test_change_password_then_login_uses_the_new_password(client: httpx.AsyncClient) -> None:
    """The new Argon2id hash is the only password that signs in."""
    token = await _token(client)
    changed = await client.post(
        "/api/v1/profile/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "correct-horse", "new_password": "new-password-1"},
    )
    assert changed.status_code == 204

    old_login = await client.post(
        "/api/v1/auth/login",
        data={"username": "ada@example.com", "password": "correct-horse"},
    )
    new_login = await client.post(
        "/api/v1/auth/login",
        data={"username": "ada@example.com", "password": "new-password-1"},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_reset_calibration_returns_to_baseline(client: httpx.AsyncClient) -> None:
    """Reset drops feedback and leaves the active offset on the baseline."""
    token = await _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post("/api/v1/profile/reset-calibration", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["baseline_offset"] == -1.5
    assert body["active_offset"] == -1.5

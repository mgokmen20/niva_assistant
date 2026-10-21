"""Wardrobe routes. Persistence uses in-memory SQLite, not a live server."""

from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import Base
from app.models.user import User

_ITEM = {
    "category": "Sweater",
    "thickness": "Thick",
    "color_name": "Black",
    "style": "Casual",
    "is_waterproof": False,
    "item_name": "Black Turtleneck Sweater",
}


@pytest_asyncio.fixture
async def wardrobe_client() -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker]]:
    """Serve the wardrobe routes against a fresh SQLite database."""
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
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def _wearer(session_factory: async_sessionmaker, email: str) -> str:
    """Insert one account and return a bearer token for it."""
    async with session_factory() as session:
        user = User(
            email=email,
            password_hash="not-a-login-secret",
            first_name="Ada",
            last_name="Lovelace",
            birth_date=date(1990, 1, 1),
        )
        session.add(user)
        await session.commit()
        return create_access_token({"sub": str(user.id)})


@pytest.mark.asyncio
async def test_wardrobe_requires_a_bearer(wardrobe_client: tuple[httpx.AsyncClient, async_sessionmaker]) -> None:
    """A guest cannot read the wardrobe."""
    client, _session_factory = wardrobe_client
    response = await client.get("/api/v1/wardrobe/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_owner_can_create_list_update_and_delete(
    wardrobe_client: tuple[httpx.AsyncClient, async_sessionmaker],
) -> None:
    """The signed-in wearer can change only their own garments."""
    client, session_factory = wardrobe_client
    owner = await _wearer(session_factory, "owner@example.com")
    other = await _wearer(session_factory, "other@example.com")
    headers = {"Authorization": f"Bearer {owner}"}

    created = await client.post("/api/v1/wardrobe/", json=_ITEM, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["item_name"] == "Black Turtleneck Sweater"
    assert body["category"] == "Sweater"
    assert body["is_waterproof"] is False
    assert body["is_active"] is True
    item_id = body["id"]

    listed = await client.get("/api/v1/wardrobe/", headers=headers)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [item_id]

    hidden = await client.get("/api/v1/wardrobe/", headers={"Authorization": f"Bearer {other}"})
    assert hidden.status_code == 200
    assert hidden.json() == []

    updated = await client.put(
        f"/api/v1/wardrobe/{item_id}",
        json={**_ITEM, "item_name": "Navy Rain Shell", "category": "Outerwear", "is_waterproof": True, "style": "Outdoor"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["item_name"] == "Navy Rain Shell"
    assert updated.json()["is_waterproof"] is True

    toggled = await client.patch(f"/api/v1/wardrobe/{item_id}/toggle-active", headers=headers)
    assert toggled.status_code == 200
    assert toggled.json()["is_active"] is False

    toggled_back = await client.patch(f"/api/v1/wardrobe/{item_id}/toggle-active", headers=headers)
    assert toggled_back.status_code == 200
    assert toggled_back.json()["is_active"] is True

    stolen = await client.delete(
        f"/api/v1/wardrobe/{item_id}",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert stolen.status_code == 404

    missing = await client.put(
        f"/api/v1/wardrobe/{uuid4()}",
        json=_ITEM,
        headers=headers,
    )
    assert missing.status_code == 404

    deleted = await client.delete(f"/api/v1/wardrobe/{item_id}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""

    empty = await client.get("/api/v1/wardrobe/", headers=headers)
    assert empty.json() == []


@pytest.mark.asyncio
async def test_unknown_category_is_rejected(
    wardrobe_client: tuple[httpx.AsyncClient, async_sessionmaker],
) -> None:
    """Category values stay inside the wardrobe vocabulary."""
    client, session_factory = wardrobe_client
    token = await _wearer(session_factory, "picker@example.com")
    response = await client.post(
        "/api/v1/wardrobe/",
        json={**_ITEM, "category": "Costume"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422

"""Niva HTTP application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.api import api_router
from .db.schema_sync import (
    ensure_recommendation_history_columns,
    ensure_user_account_columns,
    ensure_user_profile_columns,
)
from .db.session import get_engine
from .models import Base

_LOCAL_FRONTEND_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create ORM tables before the application serves traffic.

    ``User``, ``UserLocation``, ``RecommendationLog``, and ``FeedbackEntry``
    are registered on ``Base.metadata``. Existing tables are left in place.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_user_profile_columns)
        await conn.run_sync(ensure_user_account_columns)
        await conn.run_sync(ensure_recommendation_history_columns)
    app.state.database_ready = True
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application and mount version 1 of the API."""
    app = FastAPI(
        title="Niva Climate & Clothing Assistant API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_LOCAL_FRONTEND_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

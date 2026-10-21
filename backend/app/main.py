"""Niva HTTP application."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .api.limiter import limiter
from .api.v1.api import api_router
from .core.config import cloudflare_credentials_configured, require_startup_settings
from .db.schema_sync import (
    ensure_recommendation_history_columns,
    ensure_user_account_columns,
    ensure_user_profile_columns,
    ensure_wardrobe_item_columns,
)
from .db.session import get_engine
from .models import Base

logger = logging.getLogger(__name__)

_LOCAL_FRONTEND_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create ORM tables before the application serves traffic.

    ``User``, ``UserLocation``, ``RecommendationLog``, ``FeedbackEntry``,
    ``UserTrip``, and ``WardrobeItem`` are registered on ``Base.metadata``.
    Existing tables are left in place. New installs create ``wardrobe_items``
    here. This project does not use Alembic.
    """
    settings = require_startup_settings()
    if not cloudflare_credentials_configured(settings):
        logger.warning(
            "Cloudflare credentials are not configured. "
            "Summaries and chat will use the local rule-based engine."
        )
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_user_profile_columns)
        await conn.run_sync(ensure_user_account_columns)
        await conn.run_sync(ensure_recommendation_history_columns)
        await conn.run_sync(ensure_wardrobe_item_columns)
    app.state.database_ready = True
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application and mount version 1 of the API."""
    app = FastAPI(
        title="Niva Climate & Clothing Assistant API",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _too_many_requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_LOCAL_FRONTEND_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Outermost: rewrite request.client from X-Forwarded-For before rate limits
    # and audit logs read it. Trust every peer because Nginx is the only publisher.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.include_router(api_router, prefix="/api/v1")
    return app


def _too_many_requests(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return the same error shape as other API failures."""
    del request, exc
    return JSONResponse(status_code=429, content={"detail": "Too many requests."})


app = create_app()

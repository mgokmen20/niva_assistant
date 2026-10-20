"""FastAPI dependencies for services and the optional database session."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.constants import ROLE_ADMIN, ROLE_PARTNER
from ..db.session import get_db, get_optional_db
from ..models.user import User
from ..services.auth_service import AuthService
from ..services.feedback_service import FeedbackService
from ..services.geocoding_service import GeocodingService
from ..services.recommendation_service import RecommendationService
from ..services.voice_chat import VoiceChatService
from ..services.weather_service import (
    SHARED_DAILY_CACHE,
    SHARED_DIURNAL_CACHE,
    SHARED_WEATHER_CACHE,
    WeatherService,
)

_bearer = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
_auth_service = AuthService()


async def get_recommendation_service() -> RecommendationService:
    """Build a recommendation service from the current environment."""
    settings = get_settings()
    return RecommendationService.create(
        WeatherService(
            cache=SHARED_WEATHER_CACHE,
            daily_cache=SHARED_DAILY_CACHE,
            diurnal_cache=SHARED_DIURNAL_CACHE,
        ),
        settings=settings,
    )


def get_voice_chat_service(
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> VoiceChatService:
    """Return the spoken-question service for the current environment."""
    settings = get_settings()
    return VoiceChatService(recommendation_service, settings=settings)


def get_feedback_service() -> FeedbackService:
    """Return the feedback calibration service."""
    return FeedbackService()


def get_geocoding_service() -> GeocodingService:
    """Return the Open-Meteo place search client."""
    return GeocodingService()


def get_weather_service() -> WeatherService:
    """Return the shared Open-Meteo client used for weather-only reads."""
    return WeatherService(
        cache=SHARED_WEATHER_CACHE,
        daily_cache=SHARED_DAILY_CACHE,
        diurnal_cache=SHARED_DIURNAL_CACHE,
    )


async def get_optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID | None:
    """Return the bearer subject when the token is valid, otherwise None.

    A missing or unreadable token keeps the recommendation available for
    a guest. Personalization is skipped in that case.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
        subject = payload.get("sub")
        if subject is None:
            return None
        return UUID(str(subject))
    except (JWTError, ValueError, KeyError):
        return None


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID:
    """Return the wearer id stored in the bearer token ``sub`` claim.

    Raises:
        HTTPException: The header is missing or the token cannot be read.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
        return UUID(str(payload["sub"]))
    except (JWTError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        ) from exc


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the wearer identified by a bearer access token.

    The token subject must be a user id. An expired token, a bad
    signature, or an unknown id is rejected.

    Raises:
        HTTPException: The token is missing, invalid, or expired, or the
            wearer is not stored.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_error
        user_id = UUID(str(subject))
    except (JWTError, ValueError) as exc:
        raise credentials_error from exc
    user = await _auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Allow only an active admin.

    Raises:
        HTTPException: The wearer is signed in but is not an admin.
    """
    if user.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )
    return user


async def require_partner_or_admin(user: User = Depends(get_current_user)) -> User:
    """Allow an active partner or admin.

    Raises:
        HTTPException: The wearer is signed in with the standard user role.
    """
    if user.role not in {ROLE_PARTNER, ROLE_ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner or admin access is required.",
        )
    return user


__all__ = [
    "get_current_user",
    "get_current_user_id",
    "require_admin",
    "require_partner_or_admin",
    "get_db",
    "get_feedback_service",
    "get_geocoding_service",
    "get_optional_db",
    "get_optional_user_id",
    "get_recommendation_service",
    "get_voice_chat_service",
    "get_weather_service",
    "oauth2_scheme",
]

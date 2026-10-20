"""Registration and login routes.

Handlers parse the body, call :class:`AuthService`, and map status codes.
Password hashing and SQL stay in the service layer.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.constants import REMEMBER_ME_EXPIRE_DAYS
from ...core.security import create_access_token, mask_ip_address
from ...models.user import User
from ...schemas.auth_schema import TokenResponse, UserRegisterRequest, UserResponse
from ...services.auth_service import AuthService, EmailAlreadyRegisteredError
from ..deps import get_current_user, get_db

router = APIRouter(tags=["auth"])
_auth_service = AuthService()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a wearer account and return the public profile.

    The password is stored only as an Argon2id hash. ``get_db`` commits
    the new row when this handler returns.
    """
    try:
        user = await _auth_service.register_user(
            db,
            email=str(body.email),
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            birth_date=body.birth_date,
            gender=body.gender or "neutral",
            phone_number=body.phone_number,
            thermal_preference=body.thermal_preference,
            environment_routine=body.environment_routine,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    remember_me: str = Form(default="false"),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Return an access token when the email and password match.

    Swagger sends the OAuth2 password form. ``username`` is the wearer email.
    ``remember_me`` issues a 30-day token for localStorage sessions. A
    successful login stores the time and the masked client network prefix.
    """
    user = await _auth_service.authenticate(
        db,
        email=form_data.username,
        password=form_data.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )
    await _auth_service.record_login(db, user, masked_ip=_masked_client_ip(request))
    lifetime = timedelta(days=REMEMBER_ME_EXPIRE_DAYS) if _remember_requested(remember_me) else None
    access_token = create_access_token({"sub": str(user.id)}, expires_delta=lifetime)
    return TokenResponse(access_token=access_token, token_type="bearer")


def _remember_requested(value: str) -> bool:
    """Return whether the login form asked for a durable session."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _masked_client_ip(request: Request) -> str:
    """Return the nDSG prefix from the forwarding header or the client host."""
    forwarded = request.headers.get("x-forwarded-for")
    raw_ip: str | None
    if forwarded is not None and forwarded.strip() != "":
        raw_ip = forwarded.split(",")[0].strip()
    elif request.client is not None:
        raw_ip = request.client.host
    else:
        raw_ip = None
    return mask_ip_address(raw_ip) or "unknown"


@router.get("/me", response_model=UserResponse)
async def read_current_user(user: User = Depends(get_current_user)) -> UserResponse:
    """Return the profile for the bearer token, including gender."""
    return UserResponse.model_validate(user)

"""Profile routes.

Handlers parse the body, call :class:`ProfileService`, and map status codes.
Password hashing and SQL stay in the service layer.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.user import User
from ...schemas.profile_schema import PasswordChangeRequest, ProfileResponse, ProfileUpdateRequest
from ...services.auth_service import EmailAlreadyRegisteredError
from ...services.profile_service import InvalidCurrentPasswordError, ProfileService
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/profile", tags=["profile"])
_profile_service = ProfileService()


@router.get("/me", response_model=ProfileResponse)
async def read_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Return the signed-in profile, baseline, active offset, and routine."""
    payload = await _profile_service.get_profile(db, user)
    return ProfileResponse.model_validate(payload)


@router.put("/me", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update the name, email, phone, thermal preference, and routine."""
    try:
        payload = await _profile_service.update_profile(
            db,
            user,
            first_name=body.first_name,
            last_name=body.last_name,
            email=str(body.email),
            phone_number=body.phone_number,
            thermal_preference=body.thermal_preference,
            environment_routine=body.environment_routine,
            gender=body.gender,
            birth_date=body.birth_date,
            preferred_language=body.preferred_language,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    return ProfileResponse.model_validate(payload)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Replace the password when the current password matches."""
    try:
        await _profile_service.change_password(
            db,
            user,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except InvalidCurrentPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        ) from exc


@router.post("/reset-calibration", response_model=ProfileResponse)
async def reset_calibration(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Clear feedback so the active offset returns to the thermal baseline."""
    payload = await _profile_service.reset_calibration(db, user)
    return ProfileResponse.model_validate(payload)

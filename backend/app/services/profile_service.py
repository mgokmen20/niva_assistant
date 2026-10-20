"""Read and update a wearer's profile without exposing the password hash."""

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import hash_password, verify_password
from ..models.recommendation import FeedbackEntry
from ..models.user import User
from ..services.auth_service import EmailAlreadyRegisteredError
from ..services.calibration import baseline_offset_for, calculate_user_thermal_offset


class InvalidCurrentPasswordError(Exception):
    """Raised when a password change does not match the stored hash."""


class ProfileService:
    """Load and change account, baseline, and password fields."""

    async def get_profile(self, db: AsyncSession, user: User) -> dict[str, object]:
        """Return the public profile plus the active calibration offset."""
        active_offset = await calculate_user_thermal_offset(user.id, db)
        return _profile_payload(user, active_offset)

    async def update_profile(
        self,
        db: AsyncSession,
        user: User,
        *,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str | None,
        thermal_preference: str,
        environment_routine: str,
        gender: str | None = None,
        birth_date: date | None = None,
        preferred_language: str | None = None,
    ) -> dict[str, object]:
        """Replace editable profile fields and refresh the baseline offset.

        Raises:
            EmailAlreadyRegisteredError: Another account already uses ``email``.
        """
        normalized_email = email.strip().lower()
        if normalized_email != user.email:
            existing = await db.execute(select(User.id).where(User.email == normalized_email))
            if existing.scalar_one_or_none() is not None:
                raise EmailAlreadyRegisteredError
        user.first_name = first_name.strip()
        user.last_name = last_name.strip()
        user.email = normalized_email
        user.phone_number = phone_number
        user.thermal_preference = thermal_preference
        user.environment_routine = environment_routine
        user.baseline_offset = baseline_offset_for(thermal_preference)
        if gender is not None:
            user.gender = gender
        if birth_date is not None:
            user.birth_date = birth_date
        if preferred_language is not None:
            user.preferred_language = preferred_language
        try:
            await db.flush()
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError from exc
        return await self.get_profile(db, user)

    async def change_password(
        self,
        db: AsyncSession,
        user: User,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        """Replace the password hash after the current password matches.

        Raises:
            InvalidCurrentPasswordError: ``current_password`` is wrong.
        """
        if not verify_password(current_password, user.password_hash):
            raise InvalidCurrentPasswordError
        user.password_hash = hash_password(new_password)
        await db.flush()

    async def reset_calibration(self, db: AsyncSession, user: User) -> dict[str, object]:
        """Delete feedback rows so the active offset returns to the baseline."""
        await db.execute(delete(FeedbackEntry).where(FeedbackEntry.user_id == user.id))
        user.cold_sensitivity_offset = 0.0
        await db.flush()
        return await self.get_profile(db, user)


def _profile_payload(user: User, active_offset: float) -> dict[str, object]:
    """Map a wearer row onto the profile response fields."""
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone_number": user.phone_number,
        "birth_date": user.birth_date,
        "gender": user.gender,
        "role": user.role,
        "thermal_preference": user.thermal_preference,
        "environment_routine": user.environment_routine,
        "baseline_offset": user.baseline_offset,
        "active_offset": active_offset,
        "preferred_language": user.preferred_language,
    }

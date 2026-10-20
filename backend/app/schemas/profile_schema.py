"""HTTP models for the wearer profile."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..core.constants import (
    ALLOWED_PREFERRED_LANGUAGES,
    ENVIRONMENT_MOSTLY_INDOOR,
    ENVIRONMENT_MOSTLY_OUTDOOR,
    THERMAL_PREFERENCE_BALANCED,
    THERMAL_PREFERENCE_COLD_SENSITIVE,
    THERMAL_PREFERENCE_WARM_SENSITIVE,
)
from ..schemas.auth_schema import ALLOWED_GENDERS
from ..services.calibration import baseline_offset_for

_THERMAL_PREFERENCES = frozenset(
    {
        THERMAL_PREFERENCE_COLD_SENSITIVE,
        THERMAL_PREFERENCE_BALANCED,
        THERMAL_PREFERENCE_WARM_SENSITIVE,
    }
)
_ROUTINES = frozenset({ENVIRONMENT_MOSTLY_INDOOR, ENVIRONMENT_MOSTLY_OUTDOOR})


def _clean_phone(value: str | None) -> str | None:
    """Keep a short phone string, and treat a blank value as absent."""
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    if len(text) > 32:
        raise ValueError("Phone number must be at most 32 characters.")
    return text


def _known_preference(value: str) -> str:
    """Return a thermal preference id, or reject an unknown label."""
    text = value.strip().lower()
    if text not in _THERMAL_PREFERENCES:
        allowed = ", ".join(sorted(_THERMAL_PREFERENCES))
        raise ValueError(f"Thermal preference must be one of: {allowed}.")
    baseline_offset_for(text)
    return text


def _known_language(value: str) -> str:
    """Return en, de, or tr, or reject an unknown language code."""
    text = value.strip().lower()
    if text not in ALLOWED_PREFERRED_LANGUAGES:
        allowed = ", ".join(sorted(ALLOWED_PREFERRED_LANGUAGES))
        raise ValueError(f"Preferred language must be one of: {allowed}.")
    return text


def _known_routine(value: str) -> str:
    """Return an environment routine id, or reject an unknown label."""
    text = value.strip().lower()
    if text not in _ROUTINES:
        allowed = ", ".join(sorted(_ROUTINES))
        raise ValueError(f"Environment routine must be one of: {allowed}.")
    return text


class ProfileUpdateRequest(BaseModel):
    """Editable account and thermal-baseline fields."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone_number: str | None = None
    thermal_preference: str
    environment_routine: str
    gender: str | None = None
    birth_date: date | None = None
    preferred_language: str | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        """Reject a blank name after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text

    @field_validator("phone_number")
    @classmethod
    def phone_must_be_short(cls, value: str | None) -> str | None:
        """Store a trimmed phone number, or nothing when it is blank."""
        return _clean_phone(value)

    @field_validator("thermal_preference")
    @classmethod
    def preference_must_be_known(cls, value: str) -> str:
        """Keep only the three thermal identities."""
        return _known_preference(value)

    @field_validator("environment_routine")
    @classmethod
    def routine_must_be_known(cls, value: str) -> str:
        """Keep only indoor and outdoor routines."""
        return _known_routine(value)

    @field_validator("gender")
    @classmethod
    def gender_must_be_allowed(cls, value: str | None) -> str | None:
        """Keep men, women, or neutral. Omit the field to leave it unchanged."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in ALLOWED_GENDERS:
            raise ValueError("Gender must be men, women, or neutral.")
        return normalized

    @field_validator("preferred_language")
    @classmethod
    def language_must_be_known(cls, value: str | None) -> str | None:
        """Keep English, Swiss German, or Turkish. Omit the field to leave it unchanged."""
        if value is None:
            return None
        return _known_language(value)

    @field_validator("birth_date")
    @classmethod
    def birth_date_must_be_plausible(cls, value: date | None) -> date | None:
        """Reject years before 1900 and dates after today."""
        if value is None:
            return None
        today = date.today()
        if value.year < 1900 or value > today:
            raise ValueError("Birth date must be between 1900 and today.")
        return value


class PasswordChangeRequest(BaseModel):
    """Current password plus the replacement password."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProfileResponse(BaseModel):
    """Profile shown in the account view, including the active offset."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    phone_number: str | None = None
    birth_date: date
    gender: str
    role: str
    thermal_preference: str
    environment_routine: str
    baseline_offset: float
    active_offset: float
    preferred_language: str = "en"

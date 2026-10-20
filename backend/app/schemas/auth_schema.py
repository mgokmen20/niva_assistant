"""HTTP models for registration, login, and access tokens."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..core.constants import (
    ENVIRONMENT_MOSTLY_INDOOR,
    ENVIRONMENT_MOSTLY_OUTDOOR,
    THERMAL_PREFERENCE_BALANCED,
)
from ..services.calibration import baseline_offset_for

ALLOWED_GENDERS: frozenset[str] = frozenset({"men", "women", "neutral"})


class UserRegisterRequest(BaseModel):
    """Account details required to register a wearer."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    birth_date: date
    gender: str | None = "neutral"
    phone_number: str | None = None
    thermal_preference: str = THERMAL_PREFERENCE_BALANCED
    environment_routine: str = ENVIRONMENT_MOSTLY_INDOOR

    @field_validator("gender")
    @classmethod
    def gender_must_be_allowed(cls, value: str | None) -> str:
        """Keep only men, women, or neutral. A blank value stays neutral."""
        if value is None or value.strip() == "":
            return "neutral"
        normalized = value.strip().lower()
        if normalized not in ALLOWED_GENDERS:
            raise ValueError("Gender must be men, women, or neutral.")
        return normalized

    @field_validator("phone_number")
    @classmethod
    def phone_must_be_short(cls, value: str | None) -> str | None:
        """Store a trimmed phone number, or nothing when it is blank."""
        if value is None:
            return None
        text = value.strip()
        if text == "":
            return None
        if len(text) > 32:
            raise ValueError("Phone number must be at most 32 characters.")
        return text

    @field_validator("thermal_preference")
    @classmethod
    def preference_must_be_known(cls, value: str) -> str:
        """Keep a known thermal identity and accept its baseline."""
        text = value.strip().lower()
        baseline_offset_for(text)
        return text

    @field_validator("environment_routine")
    @classmethod
    def routine_must_be_known(cls, value: str) -> str:
        """Keep only indoor and outdoor routines."""
        text = value.strip().lower()
        if text not in {ENVIRONMENT_MOSTLY_INDOOR, ENVIRONMENT_MOSTLY_OUTDOOR}:
            raise ValueError("Environment routine must be mostly_indoor or mostly_outdoor.")
        return text


class UserLoginRequest(BaseModel):
    """Credentials for an existing wearer."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Signed access token returned after authentication."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public account fields. The password hash is never included."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    birth_date: date
    role: str
    gender: str | None = "neutral"

"""HTTP models for admin account management."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..core.constants import (
    ALLOWED_ROLES,
    ENVIRONMENT_MOSTLY_INDOOR,
    ENVIRONMENT_MOSTLY_OUTDOOR,
    ROLE_USER,
    THERMAL_PREFERENCE_BALANCED,
)
from ..services.calibration import baseline_offset_for


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


def _known_role(value: str) -> str:
    """Return a role id, or reject an unknown label."""
    text = value.strip().lower()
    if text not in ALLOWED_ROLES:
        allowed = ", ".join(sorted(ALLOWED_ROLES))
        raise ValueError(f"Role must be one of: {allowed}.")
    return text


class AdminUserCreateRequest(BaseModel):
    """Account an admin can create, including its role."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    birth_date: date
    role: str = ROLE_USER
    gender: str | None = "neutral"
    phone_number: str | None = None
    thermal_preference: str = THERMAL_PREFERENCE_BALANCED
    environment_routine: str = ENVIRONMENT_MOSTLY_INDOOR

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        """Reject a blank name after surrounding whitespace is removed."""
        text = value.strip()
        if text == "":
            raise ValueError("Must not be blank.")
        return text

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, value: str) -> str:
        """Keep user, partner, or admin."""
        return _known_role(value)

    @field_validator("phone_number")
    @classmethod
    def phone_must_be_short(cls, value: str | None) -> str | None:
        """Store a trimmed phone number, or nothing when it is blank."""
        return _clean_phone(value)

    @field_validator("thermal_preference")
    @classmethod
    def preference_must_be_known(cls, value: str) -> str:
        """Keep a known thermal identity."""
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

    @field_validator("gender")
    @classmethod
    def gender_must_be_allowed(cls, value: str | None) -> str:
        """Keep men, women, or neutral."""
        if value is None or value.strip() == "":
            return "neutral"
        normalized = value.strip().lower()
        if normalized not in {"men", "women", "neutral"}:
            raise ValueError("Gender must be men, women, or neutral.")
        return normalized


class AdminUserUpdateRequest(BaseModel):
    """Fields an admin may change. Omitted fields stay as they are."""

    role: str | None = None
    is_active: bool | None = None
    phone_number: str | None = None
    thermal_preference: str | None = None
    environment_routine: str | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, value: str | None) -> str | None:
        """Keep a known role when the field is present."""
        if value is None:
            return None
        return _known_role(value)

    @field_validator("phone_number")
    @classmethod
    def phone_must_be_short(cls, value: str | None) -> str | None:
        """Store a trimmed phone number, or nothing when it is blank."""
        return _clean_phone(value)

    @field_validator("thermal_preference")
    @classmethod
    def preference_must_be_known(cls, value: str | None) -> str | None:
        """Keep a known thermal identity when the field is present."""
        if value is None:
            return None
        text = value.strip().lower()
        baseline_offset_for(text)
        return text

    @field_validator("environment_routine")
    @classmethod
    def routine_must_be_known(cls, value: str | None) -> str | None:
        """Keep only indoor and outdoor routines when the field is present."""
        if value is None:
            return None
        text = value.strip().lower()
        if text not in {ENVIRONMENT_MOSTLY_INDOOR, ENVIRONMENT_MOSTLY_OUTDOOR}:
            raise ValueError("Environment routine must be mostly_indoor or mostly_outdoor.")
        return text


class AdminPasswordResetRequest(BaseModel):
    """Replacement password chosen by an admin."""

    new_password: str = Field(min_length=8, max_length=128)


class AdminUserResponse(BaseModel):
    """Account row shown to an admin. The password hash is never included."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str | None = None
    role: str
    is_active: bool
    baseline_offset: float
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    created_at: datetime


class AdminUserListResponse(BaseModel):
    """One page of admin account rows."""

    items: list[AdminUserResponse]
    total: int
    page: int
    page_size: int


class PurgeLogsRequest(BaseModel):
    """Interval of recommendation history an admin wants to remove.

    ``before_date`` removes rows strictly older than that UTC date.
    ``start_date`` and ``end_date`` remove one inclusive calendar span.
    ``export_first`` builds the anonymized CSV archive before any delete.
    """

    before_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    export_first: bool


class PurgeLogsResponse(BaseModel):
    """Rows removed by one purge."""

    purged_count: int
    purged_recommendations: int
    purged_feedback: int


class PurgePreviewResponse(BaseModel):
    """Rows that a purge would remove. Nothing is deleted."""

    matching_count: int
    matching_recommendations: int
    matching_feedback: int

"""Wearer account and saved-location tables.

These models store personal data. ``last_login_ip`` and recommendation
logs keep only the nDSG network prefix from ``mask_ip_address``. Neither
table has a column for the raw client address.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
    true as sql_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from .base import Base


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class User(Base):
    """A registered wearer.

    ``password_hash`` stores an Argon2id hash, never a plain password.
    ``cold_sensitivity_offset`` is the personal comfort shift in degrees
    Celsius. ``birth_date`` is used only to derive age for the thermal
    engine.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "gender IN ('men', 'women', 'neutral')",
            name="ck_users_gender",
        ),
        CheckConstraint(
            "thermal_preference IN ('cold_sensitive', 'balanced', 'warm_sensitive')",
            name="ck_users_thermal_preference",
        ),
        CheckConstraint(
            "environment_routine IN ('mostly_indoor', 'mostly_outdoor')",
            name="ck_users_environment_routine",
        ),
        CheckConstraint(
            "role IN ('user', 'partner', 'admin')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "preferred_language IN ('en', 'de', 'tr')",
            name="ck_users_preferred_language",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="user",
        server_default="user",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sql_true(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gender: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="neutral",
        server_default="neutral",
    )
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    thermal_preference: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="balanced",
        server_default="balanced",
    )
    environment_routine: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="mostly_indoor",
        server_default="mostly_indoor",
    )
    baseline_offset: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0",
    )
    cold_sensitivity_offset: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    preferred_language: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="en",
        server_default="en",
    )
    is_senior_mode_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    locations: Mapped[list["UserLocation"]] = relationship(back_populates="user")
    wardrobe_items: Mapped[list["WardrobeItem"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        """Return an id-only representation so logs omit personal data."""
        return f"User(id={self.id!s})"


class UserLocation(Base):
    """A named coordinate saved for a wearer."""

    __tablename__ = "user_locations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    city_name: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="locations")

    def __repr__(self) -> str:
        """Return an id-only representation."""
        return f"UserLocation(id={self.id!s})"

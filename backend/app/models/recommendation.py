"""Persisted recommendations and wearer feedback.

    ``client_ip_masked`` must already be the nDSG-minimised prefix from
    ``mask_ip_address``. This table has no column for a raw client address.
    ``temperature_band`` is the effective-temperature bucket shown with the outfit.
Deleting a user sets ``user_id`` to null so the weather record can remain
without a direct identifier.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from ..core.constants import FEEDBACK_MAX_OFFSET, FEEDBACK_MIN_OFFSET
from .base import Base
from .user import User


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RecommendationLog(Base):
    """One clothing recommendation that was shown to a wearer or guest."""

    __tablename__ = "recommendation_logs"
    __table_args__ = (
        CheckConstraint(
            "gender IN ('male', 'female', 'other', 'unspecified')",
            name="ck_recommendation_logs_gender",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    location_name: Mapped[str] = mapped_column(String(120), nullable=False)
    air_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    effective_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_layers: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    decision_engine_used: Mapped[str] = mapped_column(String(32), nullable=False)
    temperature_band: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")
    gender: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="unspecified",
        server_default="unspecified",
    )
    client_ip_masked: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    user: Mapped[User | None] = relationship()
    feedback_entries: Mapped[list["FeedbackEntry"]] = relationship(back_populates="recommendation")

    def __repr__(self) -> str:
        """Return an id-only representation."""
        return f"RecommendationLog(id={self.id!s})"


class FeedbackEntry(Base):
    """Wearer response to one recommendation.

    ``applied_delta`` is the comfort shift they asked for, in degrees
    Celsius, and is limited to the feedback bounds.
    """

    __tablename__ = "feedback_entries"
    __table_args__ = (
        CheckConstraint(
            "applied_delta >= "
            f"{FEEDBACK_MIN_OFFSET} AND applied_delta <= {FEEDBACK_MAX_OFFSET}",
            name="ck_feedback_entry_applied_delta_bounds",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    recommendation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("recommendation_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thermal_rating: Mapped[str] = mapped_column(String(32), nullable=False)
    followed_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    applied_delta: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    recommendation: Mapped[RecommendationLog] = relationship(back_populates="feedback_entries")
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        """Return an id-only representation."""
        return f"FeedbackEntry(id={self.id!s})"

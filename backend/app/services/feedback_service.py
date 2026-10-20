"""Learn a wearer's comfort offset from recommendation feedback.

``cold_sensitivity_offset`` records the feedback step. A colder rating
stores a positive step. Clothing does not add that field: the decision
uses the calibration offset, where feeling cold is negative and is added
to the apparent temperature. The stored feedback step stays inside the
feedback bounds.
"""

import math
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.constants import (
    FEEDBACK_MAX_OFFSET,
    FEEDBACK_MIN_OFFSET,
    FEEDBACK_STEP_CELSIUS,
)
from ..models.recommendation import FeedbackEntry, RecommendationLog
from ..models.user import User

_HALF_FEEDBACK_STEP_CELSIUS: Final[float] = FEEDBACK_STEP_CELSIUS / 2.0
_RATING_DELTAS_CELSIUS: Final[dict[str, float]] = {
    "TOO_COLD": FEEDBACK_STEP_CELSIUS,
    "SLIGHTLY_COLD": _HALF_FEEDBACK_STEP_CELSIUS,
    "PERFECT": 0.0,
    "SLIGHTLY_WARM": -_HALF_FEEDBACK_STEP_CELSIUS,
    "TOO_WARM": -FEEDBACK_STEP_CELSIUS,
}
ALLOWED_THERMAL_RATINGS: Final[frozenset[str]] = frozenset(_RATING_DELTAS_CELSIUS)


def _finite_number(name: str, value: float) -> float:
    """Return ``value`` as a finite float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


class FeedbackService:
    """Update a wearer's cold-sensitivity offset from one rating."""

    def calculate_feedback_delta(self, rating: str) -> float:
        """Return the Celsius step for a thermal rating.

        ``TOO_COLD`` and ``TOO_WARM`` move a full feedback step (0.5 °C).
        ``SLIGHTLY_COLD`` and ``SLIGHTLY_WARM`` move half a step (0.25 °C).
        ``PERFECT`` does not move the offset. A positive delta means the
        wearer reported being cold. The clothing decision does not add
        this step; calibration applies the opposite sign to the apparent
        temperature.

        Args:
            rating: One of the five thermal rating labels.

        Returns:
            The signed delta in degrees Celsius.

        Raises:
            ValueError: ``rating`` is not one of the known labels.
        """
        normalized = rating.strip().upper()
        if normalized not in _RATING_DELTAS_CELSIUS:
            allowed = ", ".join(sorted(_RATING_DELTAS_CELSIUS))
            raise ValueError(f"Rating must be one of: {allowed}.")
        return _RATING_DELTAS_CELSIUS[normalized]

    def apply_offset_bounds(self, current_offset: float, delta: float) -> float:
        """Add ``delta`` and clamp the sum to the feedback bounds.

        The result is never below ``FEEDBACK_MIN_OFFSET`` (-5.0) and never
        above ``FEEDBACK_MAX_OFFSET`` (5.0).

        Args:
            current_offset: The wearer's offset before this rating.
            delta: Signed change from :meth:`calculate_feedback_delta`.

        Returns:
            The clamped offset in degrees Celsius.

        Raises:
            ValueError: Either input is not a finite number.
        """
        current = _finite_number("current_offset", current_offset)
        change = _finite_number("delta", delta)
        updated = current + change
        if updated < FEEDBACK_MIN_OFFSET:
            return FEEDBACK_MIN_OFFSET
        if updated > FEEDBACK_MAX_OFFSET:
            return FEEDBACK_MAX_OFFSET
        return updated

    async def process_user_feedback(
        self,
        db: AsyncSession,
        user_id: UUID,
        recommendation_id: UUID,
        rating: str,
        followed: bool,
    ) -> dict[str, float]:
        """Store feedback and update the wearer's clamped comfort offset.

        The session is flushed and left for the caller to commit. ``get_db``
        commits when the request succeeds.

        Args:
            db: Open async session.
            user_id: Wearer who submitted the rating.
            recommendation_id: Recommendation the rating refers to.
            rating: Thermal rating label.
            followed: Whether the wearer wore the recommended outfit.

        Returns:
            ``previous_offset``, ``new_offset``, and ``delta_applied``.
            ``delta_applied`` is the rating step. ``new_offset`` is that
            step added to the previous offset, after clamping.

        Raises:
            ValueError: The rating is unknown, a record is missing, or the
                recommendation belongs to a different wearer.
        """
        delta = self.calculate_feedback_delta(rating)
        user = await db.get(User, user_id)
        if user is None:
            raise ValueError("User was not found.")
        recommendation = await db.get(RecommendationLog, recommendation_id)
        if recommendation is None:
            raise ValueError("Recommendation was not found.")
        if recommendation.user_id is not None and recommendation.user_id != user_id:
            raise ValueError("Recommendation does not belong to this user.")
        previous_offset = _finite_number(
            "cold_sensitivity_offset",
            user.cold_sensitivity_offset,
        )
        new_offset = self.apply_offset_bounds(previous_offset, delta)
        user.cold_sensitivity_offset = new_offset
        db.add(
            FeedbackEntry(
                recommendation_id=recommendation_id,
                user_id=user_id,
                thermal_rating=rating.strip().upper(),
                followed_recommendation=followed,
                applied_delta=delta,
            )
        )
        await db.flush()
        return {
            "previous_offset": previous_offset,
            "new_offset": new_offset,
            "delta_applied": delta,
        }

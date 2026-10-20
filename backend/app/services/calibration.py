"""Turn recent thermal ratings into one clothing decision offset.

The offset is applied as ``T_decision = T_feels_like + delta_user``.
Feeling cold easily is a negative value, so adding it treats the
apparent temperature as colder and selects warmer layers. The running
value starts at the wearer's baseline. Guests stay at 0.0 °C.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.constants import (
    BASELINE_OFFSET_BALANCED_CELSIUS,
    BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS,
    BASELINE_OFFSET_WARM_SENSITIVE_CELSIUS,
    CALIBRATION_COLD_STEP_CELSIUS,
    CALIBRATION_HISTORY_LIMIT,
    CALIBRATION_MAX_OFFSET_CELSIUS,
    CALIBRATION_MIN_OFFSET_CELSIUS,
    CALIBRATION_PERFECT_PULL_CELSIUS,
    CALIBRATION_WARM_STEP_CELSIUS,
    THERMAL_PREFERENCE_BALANCED,
    THERMAL_PREFERENCE_COLD_SENSITIVE,
    THERMAL_PREFERENCE_WARM_SENSITIVE,
)
from ..domain.thermal_engine import age_in_years
from ..models.recommendation import FeedbackEntry
from ..models.user import User

_DEFAULT_ADULT_AGE_YEARS = 30

_RATING_TOO_COLD = "TOO_COLD"
_RATING_TOO_WARM = "TOO_WARM"
_RATING_PERFECT = "PERFECT"


def accumulate_thermal_offset(
    ratings_oldest_first: list[str],
    baseline: float = 0.0,
) -> float:
    """Fold ratings into one offset, starting from the wearer baseline.

    ``baseline`` is the registration offset. ``TOO_COLD`` subtracts 0.5 °C.
    ``TOO_WARM`` adds 0.5 °C. ``PERFECT`` moves the running value 0.25 °C
    toward 0. Other labels are ignored. The returned value stays inside
    [-3.0, +3.0] °C.

    Args:
        ratings_oldest_first: Thermal rating labels, oldest first.
        baseline: Starting offset in degrees Celsius.

    Returns:
        The clamped wearer offset in degrees Celsius.
    """
    offset = float(baseline)
    for rating in ratings_oldest_first:
        normalized = rating.strip().upper()
        if normalized == _RATING_TOO_COLD:
            offset += CALIBRATION_COLD_STEP_CELSIUS
        elif normalized == _RATING_TOO_WARM:
            offset += CALIBRATION_WARM_STEP_CELSIUS
        elif normalized == _RATING_PERFECT:
            offset = _pull_toward_zero(offset)
    return _clamp_calibration_offset(offset)


def _pull_toward_zero(offset: float) -> float:
    """Move ``offset`` one perfect-rating step toward 0 without crossing it."""
    if offset > 0.0:
        return max(0.0, offset - CALIBRATION_PERFECT_PULL_CELSIUS)
    if offset < 0.0:
        return min(0.0, offset + CALIBRATION_PERFECT_PULL_CELSIUS)
    return 0.0


def _clamp_calibration_offset(offset: float) -> float:
    """Keep a calibration offset inside the closed [-3.0, +3.0] interval."""
    if offset < CALIBRATION_MIN_OFFSET_CELSIUS:
        return CALIBRATION_MIN_OFFSET_CELSIUS
    if offset > CALIBRATION_MAX_OFFSET_CELSIUS:
        return CALIBRATION_MAX_OFFSET_CELSIUS
    return offset


def baseline_offset_for(preference: str) -> float:
    """Return the registration offset for a thermal preference.

    Raises:
        ValueError: ``preference`` is not a known thermal identity.
    """
    offsets = {
        THERMAL_PREFERENCE_COLD_SENSITIVE: BASELINE_OFFSET_COLD_SENSITIVE_CELSIUS,
        THERMAL_PREFERENCE_BALANCED: BASELINE_OFFSET_BALANCED_CELSIUS,
        THERMAL_PREFERENCE_WARM_SENSITIVE: BASELINE_OFFSET_WARM_SENSITIVE_CELSIUS,
    }
    key = preference.strip().lower()
    if key not in offsets:
        allowed = ", ".join(sorted(offsets))
        raise ValueError(f"Thermal preference must be one of: {allowed}.")
    return offsets[key]


async def calculate_user_thermal_offset(user_id: UUID, db: AsyncSession) -> float:
    """Return the wearer's active offset from baseline plus recent ratings.

    At most ``CALIBRATION_HISTORY_LIMIT`` rows are read, newest first, then
    applied from oldest to newest on top of ``baseline_offset``. No rows
    returns that baseline. An unknown wearer returns 0.0 °C.

    Args:
        user_id: Authenticated wearer.
        db: Open async session.

    Returns:
        Clamped offset in degrees Celsius.
    """
    baseline_row = await db.execute(select(User.baseline_offset).where(User.id == user_id))
    baseline = baseline_row.scalar_one_or_none()
    if baseline is None:
        return 0.0
    statement = (
        select(FeedbackEntry.thermal_rating)
        .where(FeedbackEntry.user_id == user_id)
        .order_by(FeedbackEntry.created_at.desc(), FeedbackEntry.id.desc())
        .limit(CALIBRATION_HISTORY_LIMIT)
    )
    result = await db.execute(statement)
    newest_first = list(result.scalars().all())
    return accumulate_thermal_offset(list(reversed(newest_first)), float(baseline))


async def wearer_age_years(user_id: UUID, db: AsyncSession, today: date | None = None) -> int:
    """Return the wearer's age in whole years, or a standard adult age.

    A missing profile uses 30 years, the same default as the recommendation
    service. The birth date is never passed through as an age.

    Args:
        user_id: Authenticated wearer.
        db: Open async session.
        today: Calendar day used for the birthday check. Defaults to today.

    Returns:
        Age in whole years, at least zero.
    """
    birth_row = await db.execute(select(User.birth_date).where(User.id == user_id))
    birth_date = birth_row.scalar_one_or_none()
    if not isinstance(birth_date, date):
        return _DEFAULT_ADULT_AGE_YEARS
    return age_in_years(birth_date, today)

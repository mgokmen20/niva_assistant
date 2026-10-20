"""Tests for feedback deltas and offset clamping."""

import pytest

from app.core.constants import FEEDBACK_MAX_OFFSET, FEEDBACK_MIN_OFFSET
from app.services.feedback_service import FeedbackService

_SERVICE = FeedbackService()


@pytest.mark.parametrize(
    ("rating", "expected_delta"),
    [
        ("TOO_COLD", 0.5),
        ("SLIGHTLY_COLD", 0.25),
        ("PERFECT", 0.0),
        ("SLIGHTLY_WARM", -0.25),
        ("TOO_WARM", -0.5),
    ],
)
def test_calculate_feedback_delta_for_every_rating(rating: str, expected_delta: float) -> None:
    """Each rating maps to its signed Celsius step."""
    assert _SERVICE.calculate_feedback_delta(rating) == expected_delta


def test_calculate_feedback_delta_rejects_an_unknown_rating() -> None:
    """An unrecognised rating is rejected before any offset changes."""
    with pytest.raises(ValueError):
        _SERVICE.calculate_feedback_delta("FREEZING")


def test_apply_offset_bounds_clamps_to_five_degrees() -> None:
    """The stored offset cannot pass +5.0 or -5.0, including large deltas."""
    assert FEEDBACK_MAX_OFFSET == 5.0
    assert FEEDBACK_MIN_OFFSET == -5.0
    assert _SERVICE.apply_offset_bounds(4.8, 0.5) == 5.0
    assert _SERVICE.apply_offset_bounds(5.0, 0.5) == 5.0
    assert _SERVICE.apply_offset_bounds(100.0, 50.0) == 5.0
    assert _SERVICE.apply_offset_bounds(-4.8, -0.5) == -5.0
    assert _SERVICE.apply_offset_bounds(-5.0, -0.5) == -5.0
    assert _SERVICE.apply_offset_bounds(-100.0, -50.0) == -5.0
    assert _SERVICE.apply_offset_bounds(1.0, 0.5) == 1.5
    assert _SERVICE.apply_offset_bounds(-1.0, -0.25) == -1.25

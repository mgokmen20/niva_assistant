"""ORM models. Importing this package registers every table on ``Base``."""

from .base import Base
from .recommendation import FeedbackEntry, RecommendationLog
from .trip import UserTrip
from .user import User, UserLocation
from .wardrobe import WardrobeItem

__all__ = [
    "Base",
    "FeedbackEntry",
    "RecommendationLog",
    "User",
    "UserLocation",
    "UserTrip",
    "WardrobeItem",
]

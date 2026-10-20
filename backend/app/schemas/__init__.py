"""Pydantic v2 DTOs for the HTTP API."""

from .auth_schema import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from .recommendation_schema import (
    FeedbackRequest,
    FeedbackResponse,
    RecommendationRequest,
    RecommendationResponse,
)

__all__ = [
    "FeedbackRequest",
    "FeedbackResponse",
    "RecommendationRequest",
    "RecommendationResponse",
    "TokenResponse",
    "UserLoginRequest",
    "UserRegisterRequest",
    "UserResponse",
]

"""Version 1 HTTP routes."""

from fastapi import APIRouter

from .endpoints_admin import router as admin_router
from .endpoints_assistant import router as assistant_router
from .endpoints_analytics import router as analytics_router
from .endpoints_auth import router as auth_router
from .endpoints_locations import router as locations_router
from .endpoints_profile import router as profile_router
from .endpoints_recommendations import router as recommendations_router
from .endpoints_travel import router as travel_router
from .endpoints_voice import router as voice_router
from .endpoints_wardrobe import router as wardrobe_router
from .endpoints_weather import router as weather_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(admin_router)
api_router.include_router(analytics_router)
api_router.include_router(profile_router)
api_router.include_router(locations_router)
api_router.include_router(recommendations_router)
api_router.include_router(voice_router)
api_router.include_router(assistant_router)
api_router.include_router(weather_router)
api_router.include_router(travel_router)
api_router.include_router(wardrobe_router)

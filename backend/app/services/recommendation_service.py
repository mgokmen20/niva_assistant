"""Orchestrate a weather fetch and one recommendation strategy.

The service does not calculate clothing itself. It selects
:class:`ClefRecommendationProvider` when Cloudflare credentials are
configured, and :class:`RuleBasedRecommendationProvider` otherwise.
"""

from typing import Any

import httpx

from ..core.config import Settings, cloudflare_credentials_configured, get_settings
from ..core.exceptions import WeatherAPIUnavailableError, WeatherServiceError
from ..domain.interfaces import IRecommendationProvider
from .diurnal import adaptability_sentence
from .llm_service import WearerDecisionContext, compose_voice_summary
from .outfit_preference import apply_outfit_preference
from .recommendation_providers import (
    ClefRecommendationProvider,
    RuleBasedRecommendationProvider,
    build_voice_summary,
    local_hour_from_weather,
)
from .weather_service import WeatherService


class RecommendationService:
    """Fetch current weather and return one finalized recommendation."""

    def __init__(
        self,
        weather_service: WeatherService,
        provider: IRecommendationProvider,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Store the weather client and the selected strategy.

        Args:
            weather_service: Open-Meteo client used to build a thermal input.
            provider: Rule-based or Clef strategy for this instance.
            settings: Used only for the spoken Cloudflare summary.
            http_client: Optional client forwarded to Clef and the summary model.
        """
        self._weather_service = weather_service
        self._provider = provider
        self._settings = settings
        self._http_client = http_client

    @classmethod
    def create(
        cls,
        weather_service: WeatherService,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> "RecommendationService":
        """Build a service, choosing Clef only when credentials are set.

        Args:
            weather_service: Open-Meteo client.
            settings: Explicit settings. When omitted, settings are loaded
                from the environment.
            http_client: Optional client forwarded to Clef. Ignored when
                the rule-based provider is selected.

        Returns:
            A service whose provider matches the credential check.
        """
        resolved = settings if settings is not None else get_settings()
        provider: IRecommendationProvider
        if cloudflare_credentials_configured(resolved):
            provider = ClefRecommendationProvider(settings=resolved, client=http_client)
        else:
            provider = RuleBasedRecommendationProvider()
        return cls(
            weather_service=weather_service,
            provider=provider,
            settings=resolved,
            http_client=http_client,
        )

    async def get_recommendation(
        self,
        latitude: float,
        longitude: float,
        age: int = 30,
        personal_offset: float = 0.0,
        city_name: str | None = None,
        first_name: str | None = None,
        outfit_preference: str = "balanced",
        language: str = "en",
        wearer_context: WearerDecisionContext | None = None,
    ) -> dict[str, Any]:
        """Return clothing layers and a spoken summary for one place.

        Args:
            latitude: Degrees north.
            longitude: Degrees east.
            age: Wearer age in whole years. Defaults to a standard adult.
            personal_offset: Comfort shift in degrees Celsius.
            city_name: Place spoken in the weather sentence. Optional.
            first_name: Signed-in wearer's given name. Guests stay unnamed.
            outfit_preference: ``light``, ``balanced``, ``warm``, or ``auto``.
            language: Spoken summary language, ``en``, ``de``, or ``tr``.
            wearer_context: Offset, routine, and recent feedback for the explanation.

        Returns:
            The provider payload, including ``voice_summary``, plus a
            ``meteorology`` block taken from the thermal observation.
        """
        raw_weather = await self._weather_service.fetch_current_weather(latitude, longitude)
        try:
            diurnal = await self._weather_service.fetch_diurnal_periods(latitude, longitude)
        except (WeatherAPIUnavailableError, WeatherServiceError):
            diurnal = []
        thermal_input = self._weather_service.to_thermal_input(
            raw_weather,
            age=age,
            personal_offset=personal_offset,
        )
        recommendation = dict(
            await self._provider.generate_recommendation(thermal_input, raw_weather)
        )
        recommendation["personal_offset"] = personal_offset
        recommendation["diurnal"] = diurnal
        spoken_preference = apply_outfit_preference(
            recommendation,
            outfit_preference,
            rain_probability_percent=thermal_input.rain_prob,
        )
        english_summary = build_voice_summary(
            recommendation,
            first_name=first_name,
            city_name=city_name,
            air_temperature_celsius=thermal_input.air_temp,
            effective_temperature_celsius=float(recommendation["effective_temperature_celsius"]),
            rain_probability_percent=thermal_input.rain_prob,
            wind_speed_mps=thermal_input.wind_speed,
            local_hour=local_hour_from_weather(raw_weather),
            outfit_preference=spoken_preference,
        )
        recommendation["voice_summary"] = await compose_voice_summary(
            language=language,
            english_summary=english_summary,
            recommendation=recommendation,
            city_name=city_name,
            air_temperature_celsius=thermal_input.air_temp,
            effective_temperature_celsius=float(recommendation["effective_temperature_celsius"]),
            wind_speed_mps=thermal_input.wind_speed,
            rain_probability_percent=thermal_input.rain_prob,
            wearer=wearer_context,
            settings=self._settings,
            http_client=self._http_client,
        )
        hint = adaptability_sentence(language, diurnal)
        if hint and hint not in recommendation["voice_summary"]:
            recommendation["voice_summary"] = f"{recommendation['voice_summary'].rstrip()} {hint}"
        recommendation["meteorology"] = {
            "air_temperature": thermal_input.air_temp,
            "apparent_temperature": thermal_input.feels_like,
            "wind_speed": thermal_input.wind_speed,
            "rain_probability": thermal_input.rain_prob,
            "uv_index": thermal_input.uv_index,
            "diurnal": diurnal,
        }
        return recommendation

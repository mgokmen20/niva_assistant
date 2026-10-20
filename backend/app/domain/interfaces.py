"""Strategy contracts for the recommendation domain.

Providers implement this interface. The interface itself stays free of HTTP
clients, web frameworks, and database libraries.
"""

from abc import ABC, abstractmethod
from typing import Any

from .thermal_engine import ThermalInput


class IRecommendationProvider(ABC):
    """One way to turn a thermal observation into a clothing recommendation."""

    @abstractmethod
    async def generate_recommendation(
        self,
        thermal_input: ThermalInput,
        raw_weather: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the recommendation payload for one observation.

        Args:
            thermal_input: Domain observation, including age and the
                wearer's personal offset.
            raw_weather: Provider forecast body that produced the
                observation. Rule-based providers may ignore it.

        Returns:
            A dictionary with clothing layers, accessories, a risk level,
            and a short voice summary.
        """

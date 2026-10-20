"""Pure thermal domain. No web or database dependencies."""

from .thermal_engine import (
    ThermalInput,
    calculate_effective_temperature,
    classify_utci_stress,
    determine_clothing_layers,
)

__all__ = [
    "ThermalInput",
    "calculate_effective_temperature",
    "classify_utci_stress",
    "determine_clothing_layers",
]

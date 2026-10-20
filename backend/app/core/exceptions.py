"""Domain and integration errors for Niva.

These types carry no web-framework or database dependency. Services raise
them when an external call or a weather payload cannot be used.
"""


class WeatherServiceError(Exception):
    """The weather payload could not be retrieved or interpreted.

    Network failures use :class:`WeatherAPIUnavailableError`, a subclass of
    this error, so callers can retry an unreachable provider separately from
    a response that arrived but is not usable.
    """


class WeatherAPIUnavailableError(WeatherServiceError):
    """Open-Meteo did not answer because of a timeout or a network failure."""


class GeocodingServiceError(Exception):
    """A place-name search could not be used.

    Network failures use :class:`GeocodingUnavailableError`.
    """


class GeocodingUnavailableError(GeocodingServiceError):
    """Open-Meteo geocoding did not answer because of a timeout or a network failure."""


class VoiceServiceError(Exception):
    """Neural speech could not be produced."""


class VoiceUnavailableError(VoiceServiceError):
    """The neural voice service did not answer or returned no audio."""

"""Runtime settings loaded from the process environment.

Cloudflare credentials and the JWT signing key are never given a real
default. An empty Cloudflare value means Clef is not configured. An empty
``SECRET_KEY`` must not be used to sign tokens. Do not log this object with
``model_dump``; ``repr`` redacts secrets.
"""

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import SECRET_KEY_MIN_LENGTH

_INSECURE_SECRET_MARKERS: tuple[str, ...] = (
    "replace-with",
    "changeme",
    "example",
    "secret",
    "default",
    "placeholder",
)
_SECRET_KEY_ERROR = "SECRET_KEY must be configured in environment variables and cannot be empty."


class Settings(BaseSettings):
    """Environment-backed configuration for Niva.

    Values are read from the process environment, then from ``.env`` and
    ``.env.local`` when those files exist. Constructor arguments still win,
    which keeps tests from depending on a developer machine.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    CLOUDFLARE_ACCOUNT_ID: str = ""
    CLOUDFLARE_API_TOKEN: str = ""
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str = ""

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_configured(cls, value: str) -> str:
        """Reject a missing, short, or placeholder signing key."""
        text = value.strip()
        folded = text.casefold()
        insecure = any(marker in folded for marker in _INSECURE_SECRET_MARKERS)
        if text == "" or len(text) < SECRET_KEY_MIN_LENGTH or insecure:
            raise ValueError(_SECRET_KEY_ERROR)
        return text

    def __repr__(self) -> str:
        """Return a representation that does not include secret values."""
        return (
            "Settings(CLOUDFLARE_ACCOUNT_ID=<redacted>, "
            "CLOUDFLARE_API_TOKEN=<redacted>, SECRET_KEY=<redacted>, "
            "DATABASE_URL=<redacted>)"
        )


def get_settings() -> Settings:
    """Load a new settings object from the current environment."""
    return Settings()


def require_startup_settings() -> Settings:
    """Load settings or stop process startup when the signing key is unusable."""
    try:
        return get_settings()
    except ValidationError as exc:
        raise RuntimeError(_SECRET_KEY_ERROR) from exc


def cloudflare_credentials_configured(settings: Settings) -> bool:
    """Return whether both Cloudflare credential fields contain a value.

    Whitespace-only strings count as missing so a blank line in ``.env``
    does not attempt a Clef call.
    """
    return bool(
        settings.CLOUDFLARE_ACCOUNT_ID.strip()
        and settings.CLOUDFLARE_API_TOKEN.strip()
    )

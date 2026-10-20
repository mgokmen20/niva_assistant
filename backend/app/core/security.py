"""Password hashing, access tokens, and IP minimisation.

Passwords use Argon2id. Access tokens are HS256 JWTs signed with
``SECRET_KEY`` from the environment. Client IPs are reduced to a network
prefix before they are stored, which is the nDSG minimisation step for
connection logs.
"""

import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import jwt

from .config import get_settings

ph: PasswordHasher = PasswordHasher()
_JWT_ALGORITHM: Final[str] = "HS256"
_UNKNOWN_IP: Final[str] = "unknown"
_IPV4_PREFIX_LENGTH: Final[int] = 24
_IPV6_PREFIX_LENGTH: Final[int] = 48


def hash_password(password: str) -> str:
    """Hash ``password`` with Argon2id.

    Args:
        password: The wearer password in plain text. It is not retained.

    Returns:
        An Argon2id encoded hash, including its salt and parameters.
    """
    return ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Return whether ``plain`` matches an Argon2id hash.

    A mismatch raises ``VerifyMismatchError`` inside argon2-cffi and is
    returned as ``False``. A hash that is not Argon2 is also ``False``.

    Args:
        plain: Password supplied at login.
        hashed: Stored Argon2id hash.

    Returns:
        ``True`` when the password matches the hash.
    """
    try:
        return ph.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Sign a JWT with HS256.

    ``exp`` is added in UTC. When ``expires_delta`` is omitted, the lifetime
    is ``ACCESS_TOKEN_EXPIRE_MINUTES`` from settings. The signing key is
    ``SECRET_KEY`` and is never written into the payload.

    Args:
        data: Claims to copy into the token, such as ``sub``.
        expires_delta: Optional lifetime. ``None`` uses the configured default.

    Returns:
        A compact JWT string.

    Raises:
        ValueError: ``SECRET_KEY`` is empty or the configured algorithm is
            not HS256.
    """
    settings = get_settings()
    if settings.SECRET_KEY.strip() == "":
        raise ValueError("SECRET_KEY is not configured.")
    if settings.ALGORITHM != _JWT_ALGORITHM:
        raise ValueError("Access tokens must use HS256.")
    lifetime = expires_delta
    if lifetime is None:
        lifetime = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    claims = dict(data)
    claims["exp"] = datetime.now(timezone.utc) + lifetime
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=_JWT_ALGORITHM)
    if isinstance(token, bytes):
        return token.decode("ascii")
    return token


def mask_ip_address(ip: str | None) -> str | None:
    """Reduce a client IP to the prefix allowed in Niva logs.

    Swiss nDSG minimisation keeps only what the audit record needs. IPv4
    addresses are truncated to a /24 network (``192.168.1.55`` becomes
    ``192.168.1.0``). IPv6 addresses are truncated to a /48 network.
    IPv4-mapped IPv6 addresses are masked as IPv4. ``None``, a blank string,
    and an unparseable value become ``unknown``.

    Args:
        ip: Raw client address, or ``None`` when the client is unknown.

    Returns:
        The network address, or ``unknown``.
    """
    if ip is None or ip.strip() == "":
        return _UNKNOWN_IP
    try:
        parsed: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return _UNKNOWN_IP
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    prefix_length = _IPV4_PREFIX_LENGTH if parsed.version == 4 else _IPV6_PREFIX_LENGTH
    network = ipaddress.ip_network(f"{parsed}/{prefix_length}", strict=False)
    return str(network.network_address)

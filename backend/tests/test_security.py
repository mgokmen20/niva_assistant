"""Tests for Argon2id passwords, HS256 access tokens, and IP minimisation."""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from jose.exceptions import ExpiredSignatureError

from app.core.security import create_access_token, hash_password, mask_ip_address, verify_password

_TEST_SECRET = "test-signing-key-for-unit-testing-32-chars-long"


@pytest.fixture
def jwt_settings(monkeypatch: pytest.MonkeyPatch) -> str:
    """Point token signing at a test key instead of a developer environment."""
    monkeypatch.setenv("SECRET_KEY", _TEST_SECRET)
    monkeypatch.setenv("ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    return _TEST_SECRET


def test_hash_password_uses_argon2id_and_verifies() -> None:
    """A password hash is salted Argon2id and matches only the same password."""
    password = "correct-horse"
    hashed = hash_password(password)
    again = hash_password(password)

    assert hashed.startswith("$argon2id$")
    assert hashed != password
    assert hashed != again
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert verify_password(password, "not-a-hash") is False


def test_create_access_token_signs_hs256_and_expires(
    jwt_settings: str,
) -> None:
    """A token carries the subject and an exp claim, and a past exp is rejected."""
    token = create_access_token(
        {"sub": "user-1"},
        expires_delta=timedelta(minutes=15),
    )
    payload = jwt.decode(token, jwt_settings, algorithms=["HS256"])
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    remaining = expires_at - datetime.now(timezone.utc)

    assert payload["sub"] == "user-1"
    assert timedelta(minutes=14) < remaining < timedelta(minutes=16)
    assert token.count(".") == 2

    expired = create_access_token(
        {"sub": "user-1"},
        expires_delta=timedelta(minutes=-1),
    )
    with pytest.raises(ExpiredSignatureError):
        jwt.decode(expired, jwt_settings, algorithms=["HS256"])


def test_create_access_token_uses_configured_lifetime(jwt_settings: str) -> None:
    """Omitting expires_delta uses ACCESS_TOKEN_EXPIRE_MINUTES."""
    before = datetime.now(timezone.utc)
    token = create_access_token({"sub": "user-2"})
    payload = jwt.decode(token, jwt_settings, algorithms=["HS256"])
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    lifetime = expires_at - before

    assert timedelta(minutes=29) < lifetime < timedelta(minutes=31)


def test_mask_ip_address_truncates_ipv4_to_24_and_ipv6_to_48() -> None:
    """Stored addresses keep a network prefix and drop the host identifier."""
    assert mask_ip_address("192.168.1.55") == "192.168.1.0"
    assert mask_ip_address(" 10.1.2.3 ") == "10.1.2.0"
    assert mask_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:db8:85a3::"
    assert mask_ip_address("2001:db8:85a3:1234:5678:8a2e:370:7334") == "2001:db8:85a3::"
    assert mask_ip_address("::ffff:192.168.1.55") == "192.168.1.0"
    assert mask_ip_address(None) == "unknown"
    assert mask_ip_address("   ") == "unknown"
    assert mask_ip_address("not-an-ip") == "unknown"

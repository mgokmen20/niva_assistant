"""Register wearers and check their passwords.

Routes call this service so SQL stays out of the HTTP handlers. The
request session is flushed here and committed by ``get_db``.
"""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import hash_password, verify_password
from ..models.user import User
from ..services.calibration import baseline_offset_for


class EmailAlreadyRegisteredError(Exception):
    """Raised when a registration email is already stored."""


class AuthService:
    """Create accounts and resolve login credentials."""

    async def register_user(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        birth_date: date,
        gender: str = "neutral",
        phone_number: str | None = None,
        thermal_preference: str = "balanced",
        environment_routine: str = "mostly_indoor",
    ) -> User:
        """Store a new wearer with an Argon2id password hash.

        Args:
            db: Open async session. The caller commits.
            email: Account email. Stored in lowercase.
            password: Plain password. Only the hash is persisted.
            first_name: Given name.
            last_name: Family name.
            birth_date: Date of birth used later for age.
            gender: Apparel imagery audience. One of men, women, or neutral.
            phone_number: Optional contact number.
            thermal_preference: Registration thermal identity.
            environment_routine: Indoor or outdoor daily routine.

        Returns:
            The new user, including the database id.

        Raises:
            EmailAlreadyRegisteredError: The email is already registered.
        """
        normalized_email = email.strip().lower()
        existing = await self._find_by_email(db, normalized_email)
        if existing is not None:
            raise EmailAlreadyRegisteredError
        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            birth_date=birth_date,
            gender=gender,
            phone_number=phone_number,
            thermal_preference=thermal_preference,
            environment_routine=environment_routine,
            baseline_offset=baseline_offset_for(thermal_preference),
        )
        db.add(user)
        try:
            await db.flush()
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError from exc
        return user

    async def authenticate(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
    ) -> User | None:
        """Return the wearer when the email and password match.

        Args:
            db: Open async session.
            email: Submitted email address.
            password: Submitted plain password.

        Returns:
            The matching user, or ``None`` when the credentials are wrong.
        """
        user = await self._find_by_email(db, email.strip().lower())
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user

    async def record_login(self, db: AsyncSession, user: User, *, masked_ip: str) -> None:
        """Store the latest successful sign-in time and masked network prefix.

        Args:
            db: Open async session. The caller commits.
            user: Wearer who just authenticated.
            masked_ip: nDSG network prefix, never the raw client address.
        """
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = masked_ip
        await db.flush()

    async def get_user_by_id(self, db: AsyncSession, user_id: UUID) -> User | None:
        """Load one wearer by primary key.

        Args:
            db: Open async session.
            user_id: Subject claim from an access token.

        Returns:
            The user, or ``None`` when that id is not stored.
        """
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _find_by_email(self, db: AsyncSession, email: str) -> User | None:
        """Return the wearer stored under ``email``, if any."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

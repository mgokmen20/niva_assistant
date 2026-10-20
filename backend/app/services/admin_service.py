"""Admin account management.

Routes call this service so SQL and password hashing stay out of handlers.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.constants import (
    ADMIN_USER_PAGE_SIZE_DEFAULT,
    ADMIN_USER_PAGE_SIZE_MAX,
    ROLE_ADMIN,
    ROLE_PARTNER,
)
from ..core.security import hash_password
from ..models.user import User
from ..services.auth_service import AuthService, EmailAlreadyRegisteredError
from ..services.calibration import baseline_offset_for


class UserNotFoundError(Exception):
    """Raised when an admin targets an id that is not stored."""


class CannotManageSelfError(Exception):
    """Raised when an admin would lock their own account."""


class StaffPasswordRequiredError(Exception):
    """Raised when a new staff account is requested without a password."""


class AdminService:
    """List, create, update, and deactivate wearer accounts."""

    def __init__(self, auth_service: AuthService | None = None) -> None:
        """Use the shared auth service unless a test supplies another one."""
        self._auth = auth_service if auth_service is not None else AuthService()

    async def list_users(
        self,
        db: AsyncSession,
        *,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = ADMIN_USER_PAGE_SIZE_DEFAULT,
    ) -> tuple[list[User], int]:
        """Return one page of accounts and the unpaged total.

        Args:
            db: Open async session.
            search: Optional text matched against name and email.
            role: Optional exact role filter.
            is_active: Optional status filter. ``None`` returns both.
            page: 1-based page number.
            page_size: Rows in the page, already bounded by the caller.

        Returns:
            The page of users, newest first, and the matching total.
        """
        filters = _user_filters(search=search, role=role, is_active=is_active)
        bounded_page = max(page, 1)
        bounded_size = min(max(page_size, 1), ADMIN_USER_PAGE_SIZE_MAX)
        total_result = await db.execute(select(func.count()).select_from(User).where(*filters))
        total = int(total_result.scalar_one())
        rows = await db.execute(
            select(User)
            .where(*filters)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((bounded_page - 1) * bounded_size)
            .limit(bounded_size)
        )
        return list(rows.scalars().all()), total

    async def create_user(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        birth_date: date,
        role: str,
        gender: str = "neutral",
        phone_number: str | None = None,
        thermal_preference: str = "balanced",
        environment_routine: str = "mostly_indoor",
    ) -> User:
        """Create an account and assign the requested role.

        Raises:
            EmailAlreadyRegisteredError: The email is already registered.
        """
        user = await self._auth.register_user(
            db,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
            gender=gender,
            phone_number=phone_number,
            thermal_preference=thermal_preference,
            environment_routine=environment_routine,
        )
        user.role = role
        await db.flush()
        return user

    async def update_user(
        self,
        db: AsyncSession,
        actor: User,
        user_id: UUID,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        phone_number: str | None = None,
        phone_was_sent: bool = False,
        thermal_preference: str | None = None,
        environment_routine: str | None = None,
    ) -> User:
        """Change role, status, phone, or thermal baseline fields.

        Raises:
            UserNotFoundError: ``user_id`` is not stored.
            CannotManageSelfError: The admin would deactivate or demote
                their own account.
        """
        user = await self._require_user(db, user_id)
        if actor.id == user.id and (
            is_active is False or (role is not None and role != user.role)
        ):
            raise CannotManageSelfError
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        if phone_was_sent:
            user.phone_number = phone_number
        if thermal_preference is not None:
            user.thermal_preference = thermal_preference
            user.baseline_offset = baseline_offset_for(thermal_preference)
        if environment_routine is not None:
            user.environment_routine = environment_routine
        await db.flush()
        return user

    async def reset_password(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        new_password: str,
    ) -> None:
        """Replace the stored Argon2id hash. The plain password is not kept.

        Raises:
            UserNotFoundError: ``user_id`` is not stored.
        """
        user = await self._require_user(db, user_id)
        user.password_hash = hash_password(new_password)
        await db.flush()

    async def deactivate_user(self, db: AsyncSession, actor: User, user_id: UUID) -> None:
        """Soft-delete an account by marking it inactive.

        Raises:
            UserNotFoundError: ``user_id`` is not stored.
            CannotManageSelfError: An admin cannot deactivate themselves.
        """
        user = await self._require_user(db, user_id)
        if actor.id == user.id:
            raise CannotManageSelfError
        user.is_active = False
        await db.flush()

    async def ensure_staff_account(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str | None,
        role: str,
        first_name: str,
        last_name: str,
    ) -> User:
        """Create a staff account when missing, then set its role.

        An existing account keeps its password. A new account needs
        ``password``.

        Raises:
            StaffPasswordRequiredError: The email is new and no password
                was supplied.
        """
        normalized = email.strip().lower()
        found = await db.execute(select(User).where(User.email == normalized))
        user = found.scalar_one_or_none()
        if user is None:
            if password is None or password.strip() == "":
                raise StaffPasswordRequiredError
            user = await self.create_user(
                db,
                email=normalized,
                password=password,
                first_name=first_name,
                last_name=last_name,
                birth_date=date(1990, 1, 1),
                role=role,
            )
            return user
        user.role = role
        user.is_active = True
        await db.flush()
        return user

    async def _require_user(self, db: AsyncSession, user_id: UUID) -> User:
        """Load one account or raise ``UserNotFoundError``."""
        user = await self._auth.get_user_by_id(db, user_id)
        if user is None:
            raise UserNotFoundError
        return user


def _like_pattern(value: str) -> str:
    """Escape LIKE wildcards and wrap the text for a contains match."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


def _user_filters(
    *,
    search: str | None,
    role: str | None,
    is_active: bool | None,
) -> list[object]:
    """Build bound filter clauses for the admin user query."""
    filters: list[object] = []
    text = "" if search is None else search.strip()
    if text != "":
        pattern = _like_pattern(text)
        full_name = func.lower(User.first_name + " " + User.last_name)
        filters.append(
            or_(
                func.lower(User.email).like(pattern, escape="\\"),
                func.lower(User.first_name).like(pattern, escape="\\"),
                func.lower(User.last_name).like(pattern, escape="\\"),
                full_name.like(pattern, escape="\\"),
            )
        )
    if role is not None:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active == is_active)
    return filters


async def seed_staff_accounts(
    db: AsyncSession,
    *,
    admin_email: str,
    admin_password: str | None,
    partner_email: str,
    partner_password: str | None,
) -> tuple[User, User]:
    """Ensure one admin account and one partner account exist.

    Returns:
        The admin user and the partner user.
    """
    service = AdminService()
    admin = await service.ensure_staff_account(
        db,
        email=admin_email,
        password=admin_password,
        role=ROLE_ADMIN,
        first_name="Niva",
        last_name="Admin",
    )
    partner = await service.ensure_staff_account(
        db,
        email=partner_email,
        password=partner_password,
        role=ROLE_PARTNER,
        first_name="Niva",
        last_name="Partner",
    )
    return admin, partner


__all__ = [
    "AdminService",
    "CannotManageSelfError",
    "StaffPasswordRequiredError",
    "UserNotFoundError",
    "seed_staff_accounts",
]

"""Admin account routes.

Handlers parse the request, call :class:`AdminService`, and map status codes.
Password hashing and SQL stay in the service layer.
"""

import logging
from collections.abc import Iterator
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.constants import (
    ADMIN_USER_PAGE_SIZE_DEFAULT,
    ADMIN_USER_PAGE_SIZE_MAX,
    ALLOWED_ROLES,
)
from ...models.user import User
from ...schemas.admin_schema import (
    AdminPasswordResetRequest,
    AdminUserCreateRequest,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
    PurgeLogsRequest,
    PurgeLogsResponse,
    PurgePreviewResponse,
)
from ...services.admin_service import (
    AdminService,
    CannotManageSelfError,
    UserNotFoundError,
)
from ...services.analytics import (
    AnalyticsWindowError,
    TimeWindow,
    build_clothing_trends_csv,
    count_historical_logs,
    purge_historical_logs,
    resolve_purge_window,
)
from ...services.auth_service import EmailAlreadyRegisteredError
from ..deps import get_db, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
_admin_service = AdminService()
_ARCHIVE_MEDIA_TYPE = "text/csv"
_ARCHIVE_FILENAME = "niva-log-archive.csv"


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    search: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=ADMIN_USER_PAGE_SIZE_DEFAULT,
        ge=1,
        le=ADMIN_USER_PAGE_SIZE_MAX,
    ),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """Return a page of accounts. Optional filters match name, email, role, and status."""
    known_role = _optional_role(role)
    users, total = await _admin_service.list_users(
        db,
        search=search,
        role=known_role,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return AdminUserListResponse(
        items=[AdminUserResponse.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    body: AdminUserCreateRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """Create an account with the role chosen by the admin."""
    try:
        user = await _admin_service.create_user(
            db,
            email=str(body.email),
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            birth_date=body.birth_date,
            role=body.role,
            gender=body.gender or "neutral",
            phone_number=body.phone_number,
            thermal_preference=body.thermal_preference,
            environment_routine=body.environment_routine,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    return AdminUserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    body: AdminUserUpdateRequest,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """Update role, active status, phone, or thermal preferences."""
    try:
        user = await _admin_service.update_user(
            db,
            actor,
            user_id,
            role=body.role,
            is_active=body.is_active,
            phone_number=body.phone_number,
            phone_was_sent="phone_number" in body.model_fields_set,
            thermal_preference=body.thermal_preference,
            environment_routine=body.environment_routine,
        )
    except UserNotFoundError as exc:
        raise _not_found() from exc
    except CannotManageSelfError as exc:
        raise _cannot_manage_self() from exc
    return AdminUserResponse.model_validate(user)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: UUID,
    body: AdminPasswordResetRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Store an Argon2id hash for the replacement password."""
    try:
        await _admin_service.reset_password(db, user_id, new_password=body.new_password)
    except UserNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete an account by marking it inactive."""
    try:
        await _admin_service.deactivate_user(db, actor, user_id)
    except UserNotFoundError as exc:
        raise _not_found() from exc
    except CannotManageSelfError as exc:
        raise _cannot_manage_self() from exc


@router.get("/maintenance/purge-preview", response_model=PurgePreviewResponse)
async def preview_purge(
    before_date: date | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PurgePreviewResponse:
    """Count recommendation history in an interval without deleting it."""
    window = _purge_window(before_date, start_date, end_date)
    measured = await count_historical_logs(db, window)
    return PurgePreviewResponse(
        matching_count=measured.total,
        matching_recommendations=measured.recommendations,
        matching_feedback=measured.feedback,
    )


@router.get("/maintenance/purge-archive")
async def download_purge_archive(
    before_date: date | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download the anonymized garment CSV for the interval about to be purged."""
    window = _purge_window(before_date, start_date, end_date)
    content = await build_clothing_trends_csv(db, window=window)
    return StreamingResponse(
        _csv_chunks(content),
        media_type=_ARCHIVE_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{_ARCHIVE_FILENAME}"'},
    )


@router.post("/maintenance/purge-logs", response_model=PurgeLogsResponse)
async def purge_logs(
    body: PurgeLogsRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PurgeLogsResponse:
    """Delete recommendation logs and feedback inside the requested interval."""
    window = _purge_window(body.before_date, body.start_date, body.end_date)
    removed = await purge_historical_logs(db, window, export_first=body.export_first)
    return PurgeLogsResponse(
        purged_count=removed.total,
        purged_recommendations=removed.recommendations,
        purged_feedback=removed.feedback,
    )


def _purge_window(before_date: date | None, start_date: date | None, end_date: date | None) -> TimeWindow:
    """Resolve a purge interval, or reject a missing or mixed boundary."""
    try:
        return resolve_purge_window(
            before_date=before_date,
            start_date=start_date,
            end_date=end_date,
        )
    except AnalyticsWindowError as exc:
        logger.warning("Log purge window was rejected.", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected dates are not valid.",
        ) from exc


def _csv_chunks(content: str) -> Iterator[str]:
    """Yield the archive body so the response can stream it."""
    yield content


def _optional_role(role: str | None) -> str | None:
    """Return a known role filter, or reject an unknown label."""
    if role is None or role.strip() == "":
        return None
    text = role.strip().lower()
    if text not in ALLOWED_ROLES:
        allowed = ", ".join(sorted(ALLOWED_ROLES))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Role must be one of: {allowed}.",
        )
    return text


def _not_found() -> HTTPException:
    """Map a missing account to 404."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User was not found.")


def _cannot_manage_self() -> HTTPException:
    """Map a self-lockout attempt to 400."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="You cannot deactivate or change the role of your own account.",
    )

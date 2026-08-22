from fastapi import APIRouter, Request

from app.auth import CurrentAdmin
from app.config import settings
from app.errors import api_error
from app.models import (
    AdminLoginInput,
    BanUserInput,
    ModerateContentInput,
    ResolveReportInput,
    SuspendUserInput,
    TokenPayload,
    UnsuspendUserInput,
)
from app.rate_limit import InMemoryRateLimiter
from app.store import store

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_login_limiter = InMemoryRateLimiter(
    max_requests=settings.admin_login_rate_limit,
    window_seconds=settings.admin_login_rate_window_seconds,
)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.post("/auth/login")
def admin_login(body: AdminLoginInput, request: Request):
    ip = _client_ip(request)
    if not _admin_login_limiter.is_allowed(f"admin-login:{ip}"):
        raise api_error(
            "API_008",
            "Too many login attempts. Please try again later.",
            429,
            retryable=True,
        )
    return store.admin_login(body.email, body.password, ip_address=ip)


@router.get("/auth/me")
def admin_me(admin: TokenPayload = CurrentAdmin):
    return {"email": admin.email, "role": admin.role, "adminId": admin.sub}


@router.get("/users")
def list_users(
    status: str | None = None,
    reported: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: TokenPayload = CurrentAdmin,
):
    if limit < 1 or limit > 100:
        raise api_error("APP_002", "Please check your input and try again.", 400, "limit must be between 1 and 100.")
    if offset < 0:
        raise api_error("APP_002", "Please check your input and try again.", 400, "offset must be >= 0.")
    if status and status not in ("active", "suspended", "banned"):
        raise api_error("APP_002", "Please check your input and try again.", 400, "Invalid status filter.")
    return store.admin_list_users(status=status, reported=reported, search=search, limit=limit, offset=offset)


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    body: SuspendUserInput,
    request: Request,
    admin: TokenPayload = CurrentAdmin,
):
    return store.admin_suspend_user(
        admin_id=admin.sub,
        admin_email=admin.email,
        user_id=user_id,
        reason=body.reason,
        duration_hours=body.durationHours,
        ip_address=_client_ip(request),
    )


@router.post("/users/{user_id}/ban")
def ban_user(
    user_id: str,
    body: BanUserInput,
    request: Request,
    admin: TokenPayload = CurrentAdmin,
):
    return store.admin_ban_user(
        admin_id=admin.sub,
        admin_email=admin.email,
        user_id=user_id,
        reason=body.reason,
        ip_address=_client_ip(request),
    )


@router.post("/users/{user_id}/unsuspend")
def unsuspend_user(
    user_id: str,
    body: UnsuspendUserInput,
    request: Request,
    admin: TokenPayload = CurrentAdmin,
):
    return store.admin_unsuspend_user(
        admin_id=admin.sub,
        admin_email=admin.email,
        user_id=user_id,
        reason=body.reason,
        ip_address=_client_ip(request),
    )


@router.get("/reports")
def list_reports(
    status: str | None = None,
    reason: str | None = None,
    reported_user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: TokenPayload = CurrentAdmin,
):
    if limit < 1 or limit > 100:
        raise api_error("APP_002", "Please check your input and try again.", 400, "limit must be between 1 and 100.")
    if offset < 0:
        raise api_error("APP_002", "Please check your input and try again.", 400, "offset must be >= 0.")
    return store.admin_list_reports(
        status=status,
        reason=reason,
        reported_user_id=reported_user_id,
        limit=limit,
        offset=offset,
    )


@router.patch("/reports/{report_id}")
def resolve_report(
    report_id: str,
    body: ResolveReportInput,
    request: Request,
    admin: TokenPayload = CurrentAdmin,
):
    return store.admin_resolve_report(
        admin_id=admin.sub,
        admin_email=admin.email,
        report_id=report_id,
        status=body.status,
        resolution=body.resolution,
        resolution_note=body.resolutionNote,
        ip_address=_client_ip(request),
    )


@router.get("/content")
def list_content(
    status: str | None = "pending",
    content_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: TokenPayload = CurrentAdmin,
):
    if limit < 1 or limit > 100:
        raise api_error("APP_002", "Please check your input and try again.", 400, "limit must be between 1 and 100.")
    if offset < 0:
        raise api_error("APP_002", "Please check your input and try again.", 400, "offset must be >= 0.")
    return store.admin_list_content(status=status, content_type=content_type, limit=limit, offset=offset)


@router.patch("/content/{content_id}")
def moderate_content(
    content_id: str,
    body: ModerateContentInput,
    request: Request,
    admin: TokenPayload = CurrentAdmin,
):
    return store.admin_moderate_content(
        admin_id=admin.sub,
        admin_email=admin.email,
        content_id=content_id,
        action=body.action,
        note=body.note,
        ip_address=_client_ip(request),
    )


@router.get("/audit-log")
def audit_log(
    action: str | None = None,
    admin_id: str | None = None,
    target_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: TokenPayload = CurrentAdmin,
):
    if limit < 1 or limit > 200:
        raise api_error("APP_002", "Please check your input and try again.", 400, "limit must be between 1 and 200.")
    if offset < 0:
        raise api_error("APP_002", "Please check your input and try again.", 400, "offset must be >= 0.")
    return store.admin_get_audit_log(
        action=action,
        admin_id=admin_id,
        target_id=target_id,
        limit=limit,
        offset=offset,
    )

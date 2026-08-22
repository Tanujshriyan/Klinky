from fastapi import APIRouter, Depends, Request, Response

from app.auth import CurrentUserId
from app.errors import api_error
from app.models import (
    LoginInput,
    PasswordResetRequestResult,
    RegisterInput,
    SocialLoginInput,
    WsTicketResponse,
)
from app.rate_limit import InMemoryRateLimiter
from app.store import store
from app.ws_tickets import issue_ws_ticket

router = APIRouter(prefix="/auth", tags=["auth"])

_auth_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=300)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit_auth(request: Request, key: str) -> None:
    if not _auth_limiter.is_allowed(f"auth:{key}:{_client_ip(request)}"):
        raise api_error(
            "API_008",
            "Too many attempts. Please try again later.",
            429,
            retryable=True,
        )


@router.post("/login")
def login(body: LoginInput, request: Request):
    _rate_limit_auth(request, f"login:{body.email.strip().lower()}")
    return store.login(body.email, body.password)


@router.post("/register")
def register(body: RegisterInput, request: Request):
    _rate_limit_auth(request, f"register:{body.email.strip().lower()}")
    return store.register(body)


@router.post("/change-password", status_code=204)
def change_password(body: dict, _user_id: str = CurrentUserId):
    store.change_password(body["currentPassword"], body["newPassword"])
    return Response(status_code=204)


@router.delete("/account", status_code=204)
def delete_account(_user_id: str = CurrentUserId):
    store.delete_account()
    return Response(status_code=204)


@router.post("/forgot-password")
def forgot_password(body: dict, request: Request) -> PasswordResetRequestResult:
    email = body.get("email", "")
    _rate_limit_auth(request, f"forgot:{email.strip().lower()}")
    return store.request_password_reset(email)


@router.post("/reset-password", status_code=204)
def reset_password(body: dict):
    store.reset_password(body["email"], body["code"], body["newPassword"])
    return Response(status_code=204)


@router.post("/change-email")
def change_email(body: dict, _user_id: str = CurrentUserId) -> PasswordResetRequestResult:
    return store.change_email(body["email"])


@router.post("/verify-email", status_code=204)
def verify_email(body: dict, _user_id: str = CurrentUserId):
    store.verify_email(body["code"])
    return Response(status_code=204)


@router.post("/social")
def social_login(body: SocialLoginInput):
    return store.social_login(body)


@router.post("/ws-ticket", response_model=WsTicketResponse)
def create_ws_ticket(user_id: str = CurrentUserId):
    return WsTicketResponse(ticket=issue_ws_ticket(user_id))

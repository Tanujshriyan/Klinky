from fastapi import APIRouter, Depends, Response

from app.auth import CurrentUserId
from app.models import (
    LoginInput,
    PasswordResetRequestResult,
    RegisterInput,
    SocialLoginInput,
)
from app.store import store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginInput):
    return store.login(body.email, body.password)


@router.post("/register")
def register(body: RegisterInput):
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
def forgot_password(body: dict) -> PasswordResetRequestResult:
    return store.request_password_reset(body["email"])


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

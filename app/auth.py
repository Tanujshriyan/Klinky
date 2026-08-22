from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Header
from jose import JWTError, jwt

from app.config import settings
from app.errors import api_error
from app.models import TokenPayload

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str, role: str = "user") -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.admin_jwt_expire_hours if role == "admin" else settings.jwt_expire_hours
    )
    payload = {"sub": user_id, "email": email, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_admin_token(admin_id: str, email: str) -> str:
    return create_access_token(admin_id, email, role="admin")


def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return TokenPayload(
            sub=data["sub"],
            email=data["email"],
            exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
            role=data.get("role", "user"),
        )
    except JWTError as exc:
        raise api_error("API_005", "Session expired. Please sign in again.", 401, str(exc)) from exc


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise api_error("AUTH_003", "You must be signed in to continue.", 401)
    return authorization.removeprefix("Bearer ").strip()


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    token = _extract_bearer_token(authorization)
    payload = decode_token(token)
    if payload.role == "admin":
        raise api_error("AUTH_003", "You must be signed in to continue.", 401, "Admin token cannot access user routes.")
    return payload.sub


async def get_current_admin(authorization: str | None = Header(default=None)) -> TokenPayload:
    token = _extract_bearer_token(authorization)
    payload = decode_token(token)
    if payload.role != "admin":
        raise api_error("API_006", "You do not have permission for this action.", 403, "Admin access required.")
    return payload


CurrentUserId = Depends(get_current_user_id)
CurrentAdmin = Depends(get_current_admin)

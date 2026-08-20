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


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return TokenPayload(
            sub=data["sub"],
            email=data["email"],
            exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
        )
    except JWTError as exc:
        raise api_error("API_005", "Session expired. Please sign in again.", 401, str(exc)) from exc


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise api_error("AUTH_003", "You must be signed in to continue.", 401)
    token = authorization.removeprefix("Bearer ").strip()
    return decode_token(token).sub


CurrentUserId = Depends(get_current_user_id)

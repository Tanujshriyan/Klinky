from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-change-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expire_hours: int = 168
    cors_origins: str = "*"
    host: str = "0.0.0.0"
    port: int = 8000
    s3_bucket: str = ""
    s3_region: str = "eu-west-1"
    s3_public_base_url: str = ""
    dev_mode: bool = True

    # Admin moderation (set in production via env — never commit real values)
    admin_email: str = ""
    admin_password_hash: str = ""
    admin_jwt_expire_hours: int = 8
    admin_login_rate_limit: int = 10
    admin_login_rate_window_seconds: int = 300


settings = Settings()


def validate_settings() -> None:
    if not settings.dev_mode and settings.jwt_secret == DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET must be set to a non-default value when DEV_MODE=false."
        )

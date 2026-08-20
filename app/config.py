from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = "dev-only-change-in-production"
    jwt_expire_hours: int = 168
    cors_origins: str = "*"
    host: str = "0.0.0.0"
    port: int = 8000
    s3_bucket: str = ""
    s3_region: str = "eu-west-1"
    s3_public_base_url: str = ""


settings = Settings()

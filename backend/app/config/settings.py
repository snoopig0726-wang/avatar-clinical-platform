from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    app_name: str = "Avatar Clinical Research Platform"
    api_prefix: str = "/api"
    secret_key: str = "local-development-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./.local-data/avatar.db"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_enabled: bool = True
    frontend_origins: str = "http://localhost:5173"
    expose_api_docs: bool = True
    access_token_ttl_minutes: int = Field(default=480, ge=15, le=1440)
    email_verification_ttl_minutes: int = Field(default=30, ge=10, le=1440)
    session_ttl_hours: int = Field(default=24, ge=1, le=72)
    retention_days: int = Field(default=30, ge=30, le=30)
    model_provider: str = "mock"
    model_name: str = "gpt-image-2"
    model_api_key: str = ""
    model_timeout_seconds: int = Field(default=180, ge=10, le=300)
    generation_dispatch_mode: str = "inline"
    storage_provider: str = "local"
    local_image_dir: str = ".local-data/avatar-images"
    s3_endpoint: str = "http://localhost:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "avatar-local"
    s3_access_key: str = "local-access-key"
    s3_secret_key: str = "local-secret-key"
    s3_region: str = "us-east-1"
    image_url_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    auto_create_tables: bool = True
    bootstrap_demo_data: bool = True
    bootstrap_example_data: bool = True
    demo_doctor_email: str = "doctor@example.com"
    demo_doctor_password: str = "Avatar-demo-2026"
    demo_doctor_name: str = "林医生"
    demo_admin_email: str = "admin@example.com"
    demo_admin_password: str = "Avatar-admin-2026"
    demo_admin_name: str = "系统管理员"

    @property
    def frontend_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self):
        if self.app_env.lower() not in {"production", "prod"}:
            return self
        unsafe: list[str] = []
        if len(self.secret_key) < 32 or "local" in self.secret_key.lower():
            unsafe.append("SECRET_KEY")
        if self.database_url.startswith("sqlite"):
            unsafe.append("DATABASE_URL")
        if "localhost" in self.redis_url:
            unsafe.append("REDIS_URL")
        if not self.rate_limit_enabled:
            unsafe.append("RATE_LIMIT_ENABLED")
        if self.auto_create_tables:
            unsafe.append("AUTO_CREATE_TABLES")
        if self.bootstrap_demo_data or self.bootstrap_example_data:
            unsafe.append("BOOTSTRAP_DEMO_DATA/BOOTSTRAP_EXAMPLE_DATA")
        if self.expose_api_docs:
            unsafe.append("EXPOSE_API_DOCS")
        if self.storage_provider != "s3":
            unsafe.append("STORAGE_PROVIDER")
        if self.s3_secret_key == "local-secret-key":
            unsafe.append("S3_SECRET_KEY")
        if self.model_provider == "mock" or not self.model_api_key:
            unsafe.append("MODEL_PROVIDER/MODEL_API_KEY")
        if any(
            "localhost" in origin or origin.startswith("http://")
            for origin in self.frontend_origin_list
        ):
            unsafe.append("FRONTEND_ORIGINS")
        if unsafe:
            raise ValueError(
                "unsafe production configuration: " + ", ".join(sorted(set(unsafe)))
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

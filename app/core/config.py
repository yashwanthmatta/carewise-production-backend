from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PLACEHOLDER_VALUES = {
    "",
    "replace-me",
    "replace-with-secret-manager-value",
    "replace-with-fernet-key",
}

DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:4173",
    "http://localhost:3000",
    "https://carewise-frontend.onrender.com",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAREWISE_", env_file=".env")

    env: str = "local"
    service_name: str = "carewise-api"
    database_url: str = "postgresql+psycopg://carewise:carewise@localhost:5432/carewise"
    redis_url: str = ""
    jwt_secret: str = "replace-me"
    field_encryption_key: str = "replace-with-fernet-key"
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    allowed_origins: str = "http://localhost:4173,http://localhost:3000"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    local_storage_dir: str = "storage"
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CAREWISE_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_ocr_model: str = Field(
        default="gpt-5.5",
        validation_alias=AliasChoices("CAREWISE_OPENAI_OCR_MODEL", "OPENAI_OCR_MODEL"),
    )
    stripe_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("CAREWISE_STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY"),
    )
    stripe_webhook_secret: str = Field(
        default="",
        validation_alias=AliasChoices("CAREWISE_STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"),
    )
    stripe_success_url: str = "https://carewise-frontend.onrender.com/?checkout=success"
    stripe_cancel_url: str = "https://carewise-frontend.onrender.com/?checkout=cancelled"
    password_reset_token_minutes: int = 30
    frontend_url: str = "https://carewise-frontend.onrender.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    auth_rate_limit_window_seconds: int = 900
    auth_rate_limit_max_attempts: int = 8
    max_report_file_bytes: int = 10 * 1024 * 1024
    allowed_report_content_types: str = "text/plain,application/pdf,image/png,image/jpeg,image/webp,image/heic"

    @staticmethod
    def clean_env_value(value: str) -> str:
        if "=" in value:
            value = value.split("=", 1)[1]
        return value.strip().strip('"').strip("'")

    @property
    def allowed_origin_list(self) -> list[str]:
        configured = {item.strip() for item in self.allowed_origins.split(",") if item.strip()}
        return sorted(configured | DEFAULT_ALLOWED_ORIGINS)

    @property
    def sqlalchemy_database_url(self) -> str:
        database_url = self.clean_env_value(self.database_url)
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return database_url

    @property
    def clean_jwt_secret(self) -> str:
        return self.clean_env_value(self.jwt_secret)

    @property
    def clean_field_encryption_key(self) -> str:
        return self.clean_env_value(self.field_encryption_key)

    @property
    def clean_otel_exporter_otlp_endpoint(self) -> str:
        return self.clean_env_value(self.otel_exporter_otlp_endpoint)

    @property
    def allowed_report_content_type_list(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_report_content_types.split(",") if item.strip()}

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def email_delivery_enabled(self) -> bool:
        return all(
            self.clean_env_value(value)
            for value in (
                self.smtp_host,
                self.smtp_username,
                self.smtp_password,
                self.smtp_from_email,
            )
        )

    def validate_for_startup(self) -> None:
        if not self.allowed_origin_list:
            raise RuntimeError("CAREWISE_ALLOWED_ORIGINS must include at least one frontend origin.")

        if not self.is_production:
            return

        missing = []
        for field_name in ("database_url", "jwt_secret", "field_encryption_key"):
            if self.clean_env_value(getattr(self, field_name)) in PLACEHOLDER_VALUES:
                missing.append(f"CAREWISE_{field_name.upper()}")

        if "localhost" in self.sqlalchemy_database_url or "@localhost" in self.sqlalchemy_database_url:
            missing.append("CAREWISE_DATABASE_URL production host")

        if missing:
            raise RuntimeError(
                "Production configuration is not ready. Set real values for: "
                + ", ".join(sorted(set(missing)))
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

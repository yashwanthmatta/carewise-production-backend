from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


PLACEHOLDER_VALUES = {
    "",
    "replace-me",
    "replace-with-secret-manager-value",
    "replace-with-fernet-key",
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
    allowed_origins: str = "http://localhost:4173,http://localhost:3000"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    @property
    def allowed_origin_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    def validate_for_startup(self) -> None:
        if not self.allowed_origin_list:
            raise RuntimeError("CAREWISE_ALLOWED_ORIGINS must include at least one frontend origin.")

        if not self.is_production:
            return

        missing = []
        for field_name in ("database_url", "jwt_secret", "field_encryption_key"):
            if getattr(self, field_name) in PLACEHOLDER_VALUES:
                missing.append(f"CAREWISE_{field_name.upper()}")

        if "localhost" in self.database_url or "@localhost" in self.database_url:
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

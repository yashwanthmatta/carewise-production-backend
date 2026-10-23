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
    "https://followthroughhealth.com",
    "https://www.followthroughhealth.com",
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
    aws_access_key_id: str = Field(
        default="",
        validation_alias=AliasChoices("AWS_ACCESS_KEY_ID", "CAREWISE_AWS_ACCESS_KEY_ID"),
    )
    aws_secret_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("AWS_SECRET_ACCESS_KEY", "CAREWISE_AWS_SECRET_ACCESS_KEY"),
    )
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CAREWISE_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_ocr_model: str = Field(
        default="gpt-5.5",
        validation_alias=AliasChoices("CAREWISE_OPENAI_OCR_MODEL", "OPENAI_OCR_MODEL"),
    )
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CAREWISE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    assistant_model: str = "claude-opus-5-5"
    # Set to true only after the "Patient Q&A safety check" workflow passes against the live model.
    # Safety switch: set to true to pause report explanations in the website while a problem is checked.
    report_explanations_paused: bool = Field(
        default=False,
        validation_alias=AliasChoices("CAREWISE_REPORT_EXPLANATIONS_PAUSED", "REPORT_EXPLANATIONS_PAUSED"),
    )
    patient_qa_safety_verified: bool = Field(
        default=False,
        validation_alias=AliasChoices("CAREWISE_PATIENT_QA_SAFETY_VERIFIED", "PATIENT_QA_SAFETY_VERIFIED"),
    )
    # While DocBridge is a synthetic-data evaluation, every patient page says so.
    docbridge_pilot_only: bool = Field(
        default=True,
        validation_alias=AliasChoices("CAREWISE_DOCBRIDGE_PILOT_ONLY", "DOCBRIDGE_PILOT_ONLY"),
    )
    # Paid-feature locks stay off until the owner decides what each plan includes;
    # until then every account gets every feature.
    entitlement_enforcement: bool = Field(
        default=False,
        validation_alias=AliasChoices("CAREWISE_ENTITLEMENT_ENFORCEMENT", "ENTITLEMENT_ENFORCEMENT"),
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
    email_verification_token_minutes: int = 60 * 24
    frontend_url: str = "https://carewise-frontend.onrender.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    auth_rate_limit_window_seconds: int = 900
    auth_rate_limit_max_attempts: int = 8
    # Phone-call pill reminders (Twilio). All four must be set for calls to go out;
    # the cron token protects the endpoint a scheduler calls every few minutes.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # A number people can call back, said at the end of the consent and reminder calls
    # (FCC rule for prerecorded calls, 47 CFR 64.1200(b)(2)). Empty: no callback line.
    reminder_callback_number: str = ""
    public_api_url: str = "https://carewise-api.onrender.com"
    reminder_cron_token: str = ""
    # DocBridge email intake. Clinics forward lab PDFs to labs+CODE@<inbound_email_domain>;
    # the email provider posts each message to /inbound/email/<inbound_email_token>.
    inbound_email_domain: str = ""
    inbound_email_token: str = ""
    # Founder-only access to feedback counts and early-access sign-ups. Set it in the
    # hosting dashboard; when empty the summary endpoint stays switched off.
    founder_token: str = ""
    # Clinician and admin roles are never self-assigned. List staff as
    # "email:role" pairs, e.g. "doctor@clinic.org:clinician,me@carewise.app:admin".
    staff_emails: str = ""

    def staff_role_for(self, email: str) -> str | None:
        wanted = (email or "").strip().lower()
        for entry in self.clean_env_value(self.staff_emails).split(","):
            address, _, role = entry.strip().partition(":")
            if address.strip().lower() == wanted and role.strip() in {"clinician", "admin"}:
                return role.strip()
        return None
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
    def inbound_email_enabled(self) -> bool:
        return bool(self.clean_env_value(self.inbound_email_domain) and self.clean_env_value(self.inbound_email_token))

    @property
    def reminder_calls_enabled(self) -> bool:
        return all(
            self.clean_env_value(value)
            for value in (self.twilio_account_sid, self.twilio_auth_token, self.twilio_from_number, self.public_api_url)
        )

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

    @property
    def storage_configuration(self) -> dict[str, str | bool]:
        backend = self.clean_env_value(self.storage_backend).lower()
        if backend == "local":
            durable = False
            ready = bool(self.clean_env_value(self.local_storage_dir))
            missing = [] if ready else ["CAREWISE_LOCAL_STORAGE_DIR"]
        elif backend == "s3":
            durable = True
            required = {
                "CAREWISE_S3_BUCKET": self.s3_bucket,
                "CAREWISE_S3_REGION": self.s3_region,
                "AWS_ACCESS_KEY_ID": self.aws_access_key_id,
                "AWS_SECRET_ACCESS_KEY": self.aws_secret_access_key,
            }
            missing = [
                name
                for name, value in required.items()
                if self.clean_env_value(value) in PLACEHOLDER_VALUES
            ]
            ready = not missing
        else:
            durable = False
            ready = False
            missing = ["CAREWISE_STORAGE_BACKEND"]

        return {
            "backend": backend,
            "durable": durable,
            "ready": ready,
            "missing": ",".join(missing),
            "bucket_configured": bool(self.clean_env_value(self.s3_bucket)),
            "endpoint_configured": bool(self.clean_env_value(self.s3_endpoint_url)),
        }

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

        storage_config = self.storage_configuration
        if not storage_config["ready"]:
            missing.extend(str(storage_config["missing"]).split(","))

        if missing:
            raise RuntimeError(
                "Production configuration is not ready. Set real values for: "
                + ", ".join(sorted(set(missing)))
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

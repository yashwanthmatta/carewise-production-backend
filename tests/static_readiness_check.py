import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    ".env.production.example",
    ".gitignore",
    "GITHUB_UPLOAD_STEPS.md",
    "app/main.py",
    "app/core/security.py",
    "app/core/rbac.py",
    "app/core/crypto.py",
    "app/db/session.py",
    "app/db/migrate.py",
    "app/models/carewise.py",
    "app/api/routes/auth.py",
    "app/api/routes/consent.py",
    "app/api/routes/patients.py",
    "app/api/routes/care_plans.py",
    "app/api/routes/clinical_review.py",
    "app/api/routes/reports.py",
    "app/api/routes/recommendations.py",
    "app/api/routes/doctors.py",
    "app/api/routes/insurance.py",
    "app/api/routes/subscriptions.py",
    "app/api/routes/notifications.py",
    "app/api/routes/admin.py",
    "app/services/queue.py",
    "app/services/telemetry.py",
    "app/workers/worker.py",
    "load-tests/k6-carewise.js",
    "load-tests/locustfile.py",
    "security/privacy_review.md",
    "security/clinical_review_workflow.md",
    "security/scale_guardrail_check.md",
    "deploy/cloud_deployment.md",
    "deploy/render/render.yaml",
    "deploy/fly/fly.toml",
    "deploy/aws/ecs-task-definition.json",
    "deploy/gcp/cloud-run-service.yaml",
    "migrations/versions/0001_initial_schema.py",
    "migrations/versions/0002_product_systems.py",
    "scripts/generate_secrets.py",
    "scripts/smoke_test_deploy.py",
    "tests/api/test_auth_consent_careplan.py",
]

REQUIRED_STRINGS = {
    "Dockerfile": ["python -m app.db.migrate", "uvicorn", "PORT"],
    "app/core/config.py": ["validate_for_startup", "Production configuration is not ready", "sqlalchemy_database_url", "clean_env_value", "carewise-frontend.onrender.com"],
    "app/core/security.py": ["create_access_token", "get_current_user", "verify_password", "clean_jwt_secret"],
    "app/core/rbac.py": ["Role", "require_roles"],
    "app/core/crypto.py": ["encrypt_field", "decrypt_field", "Fernet", "hashlib.sha256"],
    "app/main.py": ["settings.validate_for_startup()", "init_local_database"],
    "app/models/carewise.py": ["PatientProfile", "CarePlan", "AuditEvent", "ConsentRecord", "location_region", "Index"],
    "migrations/env.py": ["settings.sqlalchemy_database_url", "config.set_main_option"],
    "app/db/migrate.py": ["command.stamp", "command.upgrade", "alembic_version", "settings.sqlalchemy_database_url"],
    "migrations/versions/0001_initial_schema.py": ["create_table", "users", "patient_profiles", "care_plans"],
    "migrations/versions/0002_product_systems.py": ["report_uploads", "report_analyses", "subscriptions", "notification_preferences"],
    "app/api/routes/reports.py": ["/upload", "/download", "/analyses", "analyze_report", "report_uploaded"],
    "app/api/routes/recommendations.py": ["RecommendationOut", "safety_notes"],
    "app/api/routes/doctors.py": ["search_doctors", "DoctorSearchOut"],
    "app/api/routes/insurance.py": ["match_insurance", "InsuranceMatchOut"],
    "app/api/routes/subscriptions.py": ["create_checkout", "SubscriptionCheckoutOut"],
    "app/api/routes/notifications.py": ["register_device", "NotificationPreferenceOut"],
    "app/api/routes/admin.py": ["admin_summary", "Role.ADMIN"],
    "app/api/routes/consent.py": ["record_consent", "consent_history", "consent_recorded"],
    "app/services/queue.py": ["Redis", "Queue", "enqueue_care_plan_generation"],
    "app/services/telemetry.py": ["OpenTelemetry", "FastAPIInstrumentor", "clean_otel_exporter_otlp_endpoint"],
    "docker-compose.yml": ["postgres", "redis", "worker"],
    "deploy/render/render.yaml": ["CAREWISE_JWT_SECRET", "CAREWISE_FIELD_ENCRYPTION_KEY", "CAREWISE_ALLOWED_ORIGINS", "plan: free"],
    "deploy/fly/fly.toml": ["CAREWISE_ALLOWED_ORIGINS", "force_https"],
    "deploy/aws/ecs-task-definition.json": ["CAREWISE_ALLOWED_ORIGINS", "CAREWISE_FIELD_ENCRYPTION_KEY"],
    "deploy/gcp/cloud-run-service.yaml": ["CAREWISE_JWT_SECRET", "CAREWISE_FIELD_ENCRYPTION_KEY"],
    "scripts/generate_secrets.py": ["CAREWISE_JWT_SECRET", "CAREWISE_FIELD_ENCRYPTION_KEY"],
    "scripts/smoke_test_deploy.py": ["/ready", "/features", "request_multipart", "/reports/upload-file", "/analyses", "/download", "/insurance/match", "/privacy/me/export", "privacy_export_analyses", "privacy_export_medications", "privacy_export_intakes", "privacy_export_care_plans", "/privacy/me"],
    ".gitignore": [".env", ".venv", "*.sqlite"],
    "GITHUB_UPLOAD_STEPS.md": ["git init", "git push", "carewise-production-backend"],
    "tests/api/test_auth_consent_careplan.py": ["TestClient", "/auth/signup", "/consent", "/care-plans/generate"],
    "../carewise-clinician-dashboard/script.js": ["/clinical-review/queue", "reviewPlan", "Bearer"],
    "../carewise-mobile-app/src/apiClient.ts": ["CareWiseApiClient", "recordConsent", "Authorization"],
}


def main():
    missing_files = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    missing_strings = {}
    for path, strings in REQUIRED_STRINGS.items():
        text = (ROOT / path).read_text()
        absent = [item for item in strings if item not in text]
        if absent:
            missing_strings[path] = absent

    passed = not missing_files and not missing_strings
    report = {
        "passed": passed,
        "required_files": len(REQUIRED_FILES),
        "missing_files": missing_files,
        "missing_strings": missing_strings,
    }
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()

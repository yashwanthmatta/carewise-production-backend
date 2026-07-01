from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin,
    auth,
    care_plans,
    clinical_review,
    consent,
    doctors,
    health,
    insurance,
    lab_trends,
    mvp,
    notifications,
    patients,
    privacy,
    recommendations,
    reports,
    subscriptions,
)
from app.core.config import settings
from app.db.init_db import init_local_database
from app.services.telemetry import configure_telemetry
from app.services.security_headers import apply_security_headers


def create_app() -> FastAPI:
    app = FastAPI(
        title="CareWise API",
        version="0.1.0",
        description="Production-oriented CareWise backend scaffold.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    configure_telemetry(app)

    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)
        apply_security_headers(response)
        return response

    app.include_router(health.router)
    app.include_router(mvp.router, tags=["carewise-mvp"])
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(consent.router, prefix="/consent", tags=["consent"])
    app.include_router(patients.router, prefix="/patients", tags=["patients"])
    app.include_router(care_plans.router, prefix="/care-plans", tags=["care-plans"])
    app.include_router(clinical_review.router, prefix="/clinical-review", tags=["clinical-review"])
    app.include_router(reports.router, prefix="/reports", tags=["reports"])
    app.include_router(lab_trends.router, prefix="/lab-trends", tags=["lab-trends"])
    app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
    app.include_router(doctors.router, prefix="/doctors", tags=["doctors"])
    app.include_router(insurance.router, prefix="/insurance", tags=["insurance"])
    app.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
    app.include_router(privacy.router, prefix="/privacy", tags=["privacy"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])

    @app.on_event("startup")
    def startup() -> None:
        settings.validate_for_startup()
        init_local_database()

    return app


app = create_app()

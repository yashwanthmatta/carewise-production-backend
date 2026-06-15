from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, care_plans, clinical_review, consent, health, patients
from app.core.config import settings
from app.db.init_db import init_local_database
from app.services.telemetry import configure_telemetry


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
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(consent.router, prefix="/consent", tags=["consent"])
    app.include_router(patients.router, prefix="/patients", tags=["patients"])
    app.include_router(care_plans.router, prefix="/care-plans", tags=["care-plans"])
    app.include_router(clinical_review.router, prefix="/clinical-review", tags=["clinical-review"])

    @app.on_event("startup")
    def startup() -> None:
        settings.validate_for_startup()
        init_local_database()

    return app


app = create_app()

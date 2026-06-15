from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.schemas.carewise import CarePlanOut, IntakeIn, QueueJobOut
from app.services.care_plan import create_care_plan
from app.services.queue import enqueue_care_plan_generation

router = APIRouter()


@router.post("/generate", response_model=CarePlanOut)
def generate_care_plan(
    payload: IntakeIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return create_care_plan(db, user.user_id, payload)


@router.post("/generate-async", response_model=QueueJobOut)
def generate_care_plan_async(
    payload: IntakeIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
):
    job_id = enqueue_care_plan_generation(user.user_id, payload.model_dump())
    return QueueJobOut(job_id=job_id, status="queued")

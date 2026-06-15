from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carewise import CarePlan
from app.schemas.carewise import ReviewDecisionIn
from app.services.audit import write_audit


def list_review_queue(db: Session, limit: int = 50, offset: int = 0) -> list[dict]:
    statement = (
        select(CarePlan)
        .where(CarePlan.status == "pending_review")
        .order_by(CarePlan.created_at.desc())
        .limit(min(limit, 100))
        .offset(max(offset, 0))
    )
    plans = db.scalars(statement).all()
    return [
        {
            "id": plan.id,
            "patient_id": plan.patient_id,
            "risk_level": plan.risk_level,
            "status": plan.status,
            "created_at": plan.created_at,
        }
        for plan in plans
    ]


def review_care_plan(db: Session, care_plan_id: str, payload: ReviewDecisionIn, clinician_id: str) -> CarePlan | None:
    plan = db.get(CarePlan, care_plan_id)
    if plan is None:
        return None
    plan.status = payload.status
    plan.clinician_note = payload.clinician_note
    plan.reviewed_at = datetime.now(timezone.utc)
    write_audit(
        db,
        clinician_id,
        plan.patient_id,
        f"care_plan_{payload.status}",
        "care_plan",
        plan.id,
        {"clinician_note_present": bool(payload.clinician_note)},
    )
    db.commit()
    return plan

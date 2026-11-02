from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carewise import CarePlan
from app.schemas.carewise import ReviewDecisionIn
from app.services.audit import write_audit


def list_review_queue(db: Session, limit: int = 50, offset: int = 0, patient_ids: list[str] | None = None) -> list[dict]:
    """Care plans waiting for review. patient_ids limits the queue to those patients (a
    clinician's care-team grants); None means every patient (legacy mode only)."""
    statement = select(CarePlan).where(CarePlan.status == "pending_review")
    if patient_ids is not None:
        statement = statement.where(CarePlan.patient_id.in_(patient_ids))
    statement = statement.order_by(CarePlan.created_at.desc()).limit(min(limit, 100)).offset(max(offset, 0))
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

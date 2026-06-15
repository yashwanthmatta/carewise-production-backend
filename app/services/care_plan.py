import json

from sqlalchemy.orm import Session

from app.core.crypto import encrypt_field
from app.models.carewise import CarePlan, Intake
from app.schemas.carewise import CarePlanOut, IntakeIn
from app.services.audit import write_audit
from app.services.safety import emergency_flags, matched_conditions, requires_clinician_review


def create_care_plan(db: Session, actor_id: str, payload: IntakeIn) -> CarePlanOut:
    flags = emergency_flags(payload.symptom_text)
    conditions = matched_conditions(payload.symptom_text)
    needs_review = requires_clinician_review(flags, conditions)
    risk_level = "emergency" if flags else ("clinician_review" if needs_review else "routine")
    recommendation = {
        "summary": "Emergency routing required." if flags else "Care navigation education generated.",
        "next_steps": [
            "Use emergency care now." if flags else "Prepare doctor visit summary.",
            "Medication changes require clinician approval.",
            "Use clinician review for complex or worsening symptoms.",
        ],
        "requires_clinician_review": needs_review,
    }
    intake = Intake(
        patient_id=payload.patient_id,
        encrypted_symptom_text=encrypt_field(payload.symptom_text),
        goals_json=json.dumps(payload.goals),
        diet_style=payload.diet_style,
        activity_level=payload.activity_level,
    )
    db.add(intake)
    db.flush()
    plan = CarePlan(
        patient_id=payload.patient_id,
        intake_id=intake.id,
        risk_level=risk_level,
        status="pending_review" if needs_review else "draft",
        emergency_flags_json=json.dumps(flags),
        matched_conditions_json=json.dumps(conditions),
        recommendation_json=json.dumps(recommendation),
    )
    db.add(plan)
    db.flush()
    write_audit(db, actor_id, payload.patient_id, "care_plan_created", "care_plan", plan.id, {"risk_level": risk_level})
    db.commit()
    return CarePlanOut(
        id=plan.id,
        patient_id=plan.patient_id,
        risk_level=plan.risk_level,
        status=plan.status,
        emergency_flags=flags,
        matched_conditions=conditions,
        recommendation=recommendation,
    )

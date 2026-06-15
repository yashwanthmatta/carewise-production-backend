from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import Medication, PatientProfile
from app.schemas.carewise import MedicationIn, PatientProfileIn
from app.services.audit import write_audit

router = APIRouter()


@router.put("/me/profile")
def upsert_my_profile(
    payload: PatientProfileIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user.user_id).one_or_none()
    if profile is None:
        profile = PatientProfile(user_id=user.user_id)
        db.add(profile)
    profile.encrypted_name = encrypt_field(payload.name)
    profile.encrypted_date_of_birth = encrypt_field(payload.date_of_birth)
    profile.sex_at_birth = payload.sex_at_birth
    profile.encrypted_conditions = encrypt_field(payload.conditions)
    profile.encrypted_allergies = encrypt_field(payload.allergies)
    profile.location_region = payload.location_region
    profile.insurance_status = payload.insurance_status
    db.flush()
    write_audit(db, user.user_id, profile.id, "profile_upserted", "patient_profile", profile.id, {})
    db.commit()
    return {"patient_id": profile.id, "status": "saved"}


@router.get("/me/profile")
def get_my_profile(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profile = db.query(PatientProfile).filter(PatientProfile.user_id == user.user_id).one_or_none()
    if profile is None:
        return {"profile": None}
    return {
        "profile": {
            "id": profile.id,
            "name": decrypt_field(profile.encrypted_name),
            "date_of_birth": decrypt_field(profile.encrypted_date_of_birth),
            "sex_at_birth": profile.sex_at_birth,
            "conditions": decrypt_field(profile.encrypted_conditions),
            "allergies": decrypt_field(profile.encrypted_allergies),
            "location_region": profile.location_region,
            "insurance_status": profile.insurance_status,
        }
    }


@router.post("/{patient_id}/medications")
def add_medication(
    patient_id: str,
    payload: MedicationIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    medication = Medication(
        patient_id=patient_id,
        encrypted_name=encrypt_field(payload.name),
        encrypted_dose=encrypt_field(payload.dose),
        encrypted_timing=encrypt_field(payload.timing),
        refill_date=payload.refill_date,
        encrypted_notes=encrypt_field(payload.notes),
    )
    db.add(medication)
    db.flush()
    write_audit(db, user.user_id, patient_id, "medication_saved", "medication", medication.id, {})
    db.commit()
    return {"id": medication.id, "status": "saved"}

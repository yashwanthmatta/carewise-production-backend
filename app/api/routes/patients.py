from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_field, encrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import CareAccessGrant, Medication, PatientProfile, User
from app.schemas.carewise import CareTeamGrantIn, MedicationIn, PatientProfileIn
from app.services.access_control import assert_patient_access
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
    assert_patient_access(db, user, patient_id)
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


# Care team: the patient decides which clinicians may see their records, for how long, and can
# take that back at any time. Only the patient who owns the profile can change it.
def _owned_profile(db: Session, user: CurrentUser, patient_id: str) -> PatientProfile:
    profile = db.get(PatientProfile, patient_id)
    if profile is None or profile.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient profile not found.")
    return profile


def _grant_out(grant: CareAccessGrant, email: str) -> dict:
    return {
        "id": grant.id,
        "clinician_email": email,
        "created_at": grant.created_at,
        "expires_at": grant.expires_at,
        "revoked_at": grant.revoked_at,
    }


@router.post("/{patient_id}/care-team")
def add_to_care_team(
    patient_id: str,
    payload: CareTeamGrantIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profile = _owned_profile(db, user, patient_id)
    email = payload.clinician_email.strip().lower()
    staff = db.scalar(select(User).where(func.lower(User.email) == email))
    # Only a verified account on the clinician list can be added; the answer does not say which
    # part failed, so the list of staff addresses cannot be probed.
    if staff is None or staff.email_verified != "true" or settings.staff_role_for(staff.email) != Role.CLINICIAN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That address is not a FollowThrough Health clinician account.")
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.days) if payload.days else None
    grant = CareAccessGrant(patient_id=profile.id, staff_user_id=staff.id, granted_by=user.user_id, expires_at=expires_at)
    db.add(grant)
    db.flush()
    write_audit(db, user.user_id, profile.id, "care_team_added", "care_access_grant", grant.id, {"days": payload.days or 0})
    db.commit()
    return _grant_out(grant, staff.email)


@router.get("/{patient_id}/care-team")
def list_care_team(
    patient_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profile = _owned_profile(db, user, patient_id)
    rows = db.execute(
        select(CareAccessGrant, User.email).join(User, User.id == CareAccessGrant.staff_user_id).where(CareAccessGrant.patient_id == profile.id).order_by(CareAccessGrant.created_at.desc())
    ).all()
    return {"items": [_grant_out(grant, email) for grant, email in rows]}


@router.delete("/{patient_id}/care-team/{grant_id}")
def remove_from_care_team(
    patient_id: str,
    grant_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profile = _owned_profile(db, user, patient_id)
    grant = db.get(CareAccessGrant, grant_id)
    if grant is None or grant.patient_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(timezone.utc)
        write_audit(db, user.user_id, profile.id, "care_team_removed", "care_access_grant", grant.id, {})
        db.commit()
    return {"id": grant.id, "revoked_at": grant.revoked_at}

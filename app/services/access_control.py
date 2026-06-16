from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.rbac import Role
from app.core.security import CurrentUser
from app.models.carewise import PatientProfile


def assert_patient_access(db: Session, user: CurrentUser, patient_id: str) -> PatientProfile:
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient profile not found.")

    if user.role in {Role.CLINICIAN, Role.ADMIN}:
        return profile

    if profile.user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this patient profile.",
        )

    return profile

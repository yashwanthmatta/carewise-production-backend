import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import Role
from app.core.security import CurrentUser
from app.models.carewise import CareAccessGrant, PatientProfile


logger = logging.getLogger(__name__)


def legacy_staff_access() -> bool:
    return settings.staff_access_mode.strip().lower() == "legacy_global"


def active_grant_filter(staff_user_id: str):
    now = datetime.now(timezone.utc)
    return (
        CareAccessGrant.staff_user_id == staff_user_id,
        CareAccessGrant.revoked_at.is_(None),
        or_(CareAccessGrant.expires_at.is_(None), CareAccessGrant.expires_at > now),
    )


def granted_patient_ids(db: Session, staff_user_id: str) -> list[str]:
    return list(db.scalars(select(CareAccessGrant.patient_id).where(*active_grant_filter(staff_user_id))).unique())


def has_care_grant(db: Session, staff_user_id: str, patient_id: str) -> bool:
    return db.scalar(select(CareAccessGrant.id).where(CareAccessGrant.patient_id == patient_id, *active_grant_filter(staff_user_id)).limit(1)) is not None


def assert_patient_access(db: Session, user: CurrentUser, patient_id: str) -> PatientProfile:
    """The owner, or a clinician the owner has added to their care team (unexpired, unrevoked).

    Admins administer the service; they get no clinical access from their role.
    """
    profile = db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient profile not found.")
    if profile.user_id == user.user_id:
        return profile
    if user.role in {Role.CLINICIAN, Role.ADMIN} and legacy_staff_access():
        return profile
    if user.role == Role.CLINICIAN and has_care_grant(db, user.user_id, patient_id):
        return profile
    logger.info("patient_access_denied role=%s", user.role)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this patient profile.",
    )

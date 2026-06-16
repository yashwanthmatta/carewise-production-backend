from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import NotificationPreference
from app.schemas.carewise import NotificationDeviceIn, NotificationPreferenceOut

router = APIRouter()


@router.post("/devices", response_model=NotificationPreferenceOut)
def register_device(
    payload: NotificationDeviceIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    preference = NotificationPreference(
        user_id=user.user_id,
        channel=payload.channel,
        device_token=payload.device_token,
        enabled=str(payload.enabled).lower(),
    )
    db.add(preference)
    db.flush()
    db.commit()
    return NotificationPreferenceOut(id=preference.id, channel=preference.channel, enabled=preference.enabled == "true")


@router.get("", response_model=list[NotificationPreferenceOut])
def list_notifications(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    preferences = db.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user.user_id)).all()
    return [
        NotificationPreferenceOut(id=preference.id, channel=preference.channel, enabled=preference.enabled == "true")
        for preference in preferences
    ]

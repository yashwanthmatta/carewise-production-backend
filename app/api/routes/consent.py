from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import ConsentRecord
from app.schemas.carewise import ConsentIn
from app.services.audit import write_audit

router = APIRouter()


@router.post("")
def record_consent(
    payload: ConsentIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    record = ConsentRecord(
        user_id=user.user_id,
        consent_type=payload.consent_type,
        version=payload.version,
        accepted=str(payload.accepted).lower(),
        region=payload.region,
        source=payload.source,
    )
    db.add(record)
    db.flush()
    write_audit(
        db,
        user.user_id,
        "",
        "consent_recorded",
        "consent_record",
        record.id,
        {
            "consent_type": payload.consent_type,
            "version": payload.version,
            "accepted": payload.accepted,
            "region": payload.region,
        },
    )
    db.commit()
    return {"id": record.id, "status": "recorded"}


@router.get("/history")
def consent_history(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    statement = (
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user.user_id)
        .order_by(ConsentRecord.created_at.desc())
        .limit(min(limit, 100))
        .offset(max(offset, 0))
    )
    records = db.scalars(statement).all()
    return {
        "items": [
            {
                "id": record.id,
                "consent_type": record.consent_type,
                "version": record.version,
                "accepted": record.accepted == "true",
                "region": record.region,
                "source": record.source,
                "created_at": record.created_at,
            }
            for record in records
        ]
    }

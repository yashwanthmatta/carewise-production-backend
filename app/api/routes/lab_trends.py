from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import LabTrend, ReportUpload
from app.schemas.carewise import LabTrendIn, LabTrendOut
from app.services.access_control import assert_patient_access
from app.services.audit import write_audit

router = APIRouter()


@router.post("", response_model=LabTrendOut)
def create_lab_trend(
    payload: LabTrendIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_patient_access(db, user, payload.patient_id)
    if payload.report_id:
        report = db.get(ReportUpload, payload.report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        if report.patient_id != payload.patient_id:
            raise HTTPException(status_code=400, detail="Report does not belong to this patient.")

    trend = LabTrend(
        patient_id=payload.patient_id,
        report_id=payload.report_id,
        test_name=payload.test_name.strip(),
        value=payload.value.strip(),
        unit=payload.unit.strip(),
        observed_on=payload.observed_on.strip(),
        flag=payload.flag.strip() or "not_sure",
        encrypted_notes=encrypt_field(payload.notes),
        source=payload.source.strip() or "manual",
    )
    db.add(trend)
    db.flush()
    write_audit(
        db,
        user.user_id,
        payload.patient_id,
        "lab_trend_saved",
        "lab_trend",
        trend.id,
        {"test_name": trend.test_name, "source": trend.source, "report_id": trend.report_id or ""},
    )
    db.commit()
    return lab_trend_out(trend)


@router.get("", response_model=list[LabTrendOut])
def list_lab_trends(
    patient_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_patient_access(db, user, patient_id)
    trends = db.scalars(
        select(LabTrend)
        .where(LabTrend.patient_id == patient_id)
        .order_by(LabTrend.observed_on.desc(), LabTrend.created_at.desc())
        .limit(200)
    ).all()
    return [lab_trend_out(trend) for trend in trends]


def lab_trend_out(trend: LabTrend) -> LabTrendOut:
    return LabTrendOut(
        id=trend.id,
        patient_id=trend.patient_id,
        report_id=trend.report_id,
        test_name=trend.test_name,
        value=trend.value,
        unit=trend.unit,
        observed_on=trend.observed_on,
        flag=trend.flag,
        notes=decrypt_field(trend.encrypted_notes),
        source=trend.source,
        created_at=trend.created_at,
    )

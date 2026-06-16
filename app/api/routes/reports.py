import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import ReportAnalysis, ReportUpload
from app.schemas.carewise import ReportAnalysisOut, ReportUploadIn, ReportUploadOut
from app.services.audit import write_audit
from app.services.safety import emergency_flags, matched_conditions, requires_clinician_review

router = APIRouter()


@router.post("/upload", response_model=ReportUploadOut)
def create_report_upload(
    payload: ReportUploadIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    report = ReportUpload(
        patient_id=payload.patient_id,
        uploaded_by=user.user_id,
        file_name=payload.file_name,
        content_type=payload.content_type,
        storage_url=payload.storage_url,
        encrypted_report_text=encrypt_field(payload.report_text),
        status="uploaded",
    )
    db.add(report)
    db.flush()
    write_audit(db, user.user_id, payload.patient_id, "report_uploaded", "report", report.id, {"file_name": payload.file_name})
    db.commit()
    return ReportUploadOut(id=report.id, patient_id=report.patient_id, file_name=report.file_name, status=report.status)


@router.get("", response_model=list[ReportUploadOut])
def list_reports(
    patient_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    reports = db.scalars(
        select(ReportUpload).where(ReportUpload.patient_id == patient_id).order_by(ReportUpload.created_at.desc()).limit(50)
    ).all()
    return [
        ReportUploadOut(id=report.id, patient_id=report.patient_id, file_name=report.file_name, status=report.status)
        for report in reports
    ]


@router.post("/{report_id}/analyze", response_model=ReportAnalysisOut)
def analyze_report(
    report_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    report = db.get(ReportUpload, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    report_text = decrypt_field(report.encrypted_report_text)
    flags = emergency_flags(report_text)
    conditions = matched_conditions(report_text)
    needs_review = requires_clinician_review(flags, conditions)
    risk_level = "emergency" if flags else ("clinician_review" if needs_review else "routine")
    summary = {
        "detected_terms": conditions,
        "emergency_flags": flags,
        "message": "Report education summary generated. This is not a diagnosis.",
    }
    recommendations = {
        "next_steps": [
            "Use emergency care now." if flags else "Prepare questions for a licensed clinician.",
            "Do not change medication without clinician approval.",
            "Upload original report to the care team if symptoms are complex or worsening.",
        ],
        "requires_clinician_review": needs_review,
    }
    analysis = ReportAnalysis(
        report_id=report.id,
        patient_id=report.patient_id,
        risk_level=risk_level,
        status="pending_review" if needs_review else "draft",
        summary_json=json.dumps(summary),
        recommendations_json=json.dumps(recommendations),
    )
    report.status = "analyzed"
    db.add(analysis)
    db.flush()
    write_audit(db, user.user_id, report.patient_id, "report_analyzed", "report_analysis", analysis.id, {"risk_level": risk_level})
    db.commit()
    return ReportAnalysisOut(
        id=analysis.id,
        report_id=report.id,
        patient_id=report.patient_id,
        risk_level=risk_level,
        status=analysis.status,
        summary=summary,
        recommendations=recommendations,
    )

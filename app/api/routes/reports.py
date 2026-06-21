import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import ReportAnalysis, ReportUpload
from app.schemas.carewise import (
    ReportAnalysisOut,
    ReportDownloadOut,
    ReportTextUpdateIn,
    ReportUploadIn,
    ReportUploadOut,
)
from app.services.access_control import assert_patient_access
from app.services.audit import write_audit
from app.services.safety import emergency_flags, matched_conditions, requires_clinician_review
from app.services.storage import create_download_url, safe_file_name, store_report_file

router = APIRouter()


@router.post("/upload", response_model=ReportUploadOut)
def create_report_upload(
    payload: ReportUploadIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_patient_access(db, user, payload.patient_id)
    report = ReportUpload(
        patient_id=payload.patient_id,
        uploaded_by=user.user_id,
        file_name=safe_file_name(payload.file_name),
        content_type=payload.content_type,
        storage_url=payload.storage_url,
        encrypted_report_text=encrypt_field(payload.report_text),
        status="uploaded",
    )
    db.add(report)
    db.flush()
    write_audit(db, user.user_id, payload.patient_id, "report_uploaded", "report", report.id, {"file_name": payload.file_name})
    db.commit()
    return report_out(report)


@router.post("/upload-file", response_model=ReportUploadOut)
async def create_report_file_upload(
    patient_id: str = Form(...),
    report_text: str = Form(""),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_patient_access(db, user, patient_id)
    report = ReportUpload(
        patient_id=patient_id,
        uploaded_by=user.user_id,
        file_name=safe_file_name(file.filename or "report-upload"),
        content_type=file.content_type or "",
        encrypted_report_text=encrypt_field(report_text),
        status="uploaded",
    )
    db.add(report)
    db.flush()
    stored_file = await store_report_file(patient_id, report.id, file)
    report.storage_key = stored_file.storage_key
    report.storage_url = stored_file.storage_url
    report.file_size_bytes = str(stored_file.file_size_bytes)
    if not report_text.strip() and stored_file.extracted_text:
        report.encrypted_report_text = encrypt_field(stored_file.extracted_text)
    write_audit(
        db,
        user.user_id,
        patient_id,
        "report_file_uploaded",
        "report",
        report.id,
        {"file_name": report.file_name, "file_size_bytes": stored_file.file_size_bytes},
    )
    db.commit()
    return report_out(report)


@router.get("", response_model=list[ReportUploadOut])
def list_reports(
    patient_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_patient_access(db, user, patient_id)
    reports = db.scalars(
        select(ReportUpload).where(ReportUpload.patient_id == patient_id).order_by(ReportUpload.created_at.desc()).limit(50)
    ).all()
    return [report_out(report) for report in reports]


@router.get("/{report_id}/download", response_model=ReportDownloadOut)
def get_report_download_url(
    report_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    report = db.get(ReportUpload, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    assert_patient_access(db, user, report.patient_id)
    download_url = create_download_url(report.storage_key)
    write_audit(
        db,
        user.user_id,
        report.patient_id,
        "report_download_url_created",
        "report",
        report.id,
        {"file_name": report.file_name},
    )
    db.commit()
    return ReportDownloadOut(
        report_id=report.id,
        file_name=report.file_name,
        download_url=download_url,
        expires_in_seconds=900,
    )


@router.put("/{report_id}/text", response_model=ReportUploadOut)
def update_report_text(
    report_id: str,
    payload: ReportTextUpdateIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    report = db.get(ReportUpload, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    assert_patient_access(db, user, report.patient_id)
    report.encrypted_report_text = encrypt_field(payload.report_text)
    report.status = "uploaded"
    write_audit(
        db,
        user.user_id,
        report.patient_id,
        "report_text_updated",
        "report",
        report.id,
        {"text_length": len(payload.report_text)},
    )
    db.commit()
    return report_out(report)


@router.post("/{report_id}/analyze", response_model=ReportAnalysisOut)
def analyze_report(
    report_id: str,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    report = db.get(ReportUpload, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    assert_patient_access(db, user, report.patient_id)

    report_text = decrypt_field(report.encrypted_report_text)
    if not report_text.strip():
        summary = {
            "detected_terms": [],
            "emergency_flags": [],
            "message": (
                "The report file was stored securely, but no readable text was available for "
                "analysis yet. This is not a diagnosis."
            ),
        }
        recommendations = {
            "next_steps": [
                "Paste OCR text or key lab values before relying on report analysis.",
                "Ask a licensed clinician to review the original report.",
                "Do not change medication or treatment based only on a stored file.",
            ],
            "requires_clinician_review": True,
        }
        analysis = ReportAnalysis(
            report_id=report.id,
            patient_id=report.patient_id,
            risk_level="needs_text",
            status="needs_readable_text",
            summary_json=json.dumps(summary),
            recommendations_json=json.dumps(recommendations),
        )
        report.status = "needs_readable_text"
        db.add(analysis)
        db.flush()
        write_audit(
            db,
            user.user_id,
            report.patient_id,
            "report_analysis_needs_text",
            "report_analysis",
            analysis.id,
            {},
        )
        db.commit()
        return ReportAnalysisOut(
            id=analysis.id,
            report_id=report.id,
            patient_id=report.patient_id,
            risk_level=analysis.risk_level,
            status=analysis.status,
            summary=summary,
            recommendations=recommendations,
        )

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


def report_out(report: ReportUpload) -> ReportUploadOut:
    return ReportUploadOut(
        id=report.id,
        patient_id=report.patient_id,
        file_name=report.file_name,
        status=report.status,
        content_type=report.content_type,
        storage_url=report.storage_url,
        file_size_bytes=int(report.file_size_bytes or 0),
    )

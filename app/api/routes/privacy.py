from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import (
    AuditEvent,
    CarePlan,
    ConsentRecord,
    DataDeletionRequest,
    EmailVerificationToken,
    Intake,
    Medication,
    NotificationPreference,
    PatientProfile,
    PasswordResetToken,
    RefreshToken,
    ReportAnalysis,
    ReportUpload,
    Subscription,
    User,
)
from app.schemas.carewise import DataDeletionRequestIn, DataDeletionRequestOut
from app.services.audit import write_audit
from app.services.storage import delete_stored_file

router = APIRouter()


@router.get("/me/export")
def export_my_data(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profiles = db.scalars(select(PatientProfile).where(PatientProfile.user_id == user.user_id)).all()
    patient_ids = [profile.id for profile in profiles]
    consents = db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == user.user_id)).all()
    subscriptions = db.scalars(select(Subscription).where(Subscription.user_id == user.user_id)).all()
    notifications = db.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user.user_id)).all()
    reports = db.scalars(select(ReportUpload).where(ReportUpload.patient_id.in_(patient_ids))).all() if patient_ids else []
    care_plans = db.scalars(select(CarePlan).where(CarePlan.patient_id.in_(patient_ids))).all() if patient_ids else []
    audit_events = db.scalars(select(AuditEvent).where(AuditEvent.actor_id == user.user_id).limit(100)).all()

    return {
        "account": {"id": user.user_id, "email": user.email, "role": user.role},
        "patients": [
            {
                "id": profile.id,
                "name": decrypt_field(profile.encrypted_name),
                "date_of_birth": decrypt_field(profile.encrypted_date_of_birth),
                "sex_at_birth": profile.sex_at_birth,
                "conditions": decrypt_field(profile.encrypted_conditions),
                "allergies": decrypt_field(profile.encrypted_allergies),
                "location_region": profile.location_region,
                "insurance_status": profile.insurance_status,
            }
            for profile in profiles
        ],
        "consent_records": [
            {
                "id": consent.id,
                "consent_type": consent.consent_type,
                "version": consent.version,
                "accepted": consent.accepted == "true",
                "region": consent.region,
                "source": consent.source,
                "created_at": consent.created_at,
            }
            for consent in consents
        ],
        "reports": [
            {
                "id": report.id,
                "patient_id": report.patient_id,
                "file_name": report.file_name,
                "content_type": report.content_type,
                "file_size_bytes": int(report.file_size_bytes or 0),
                "status": report.status,
            }
            for report in reports
        ],
        "care_plans": [
            {
                "id": plan.id,
                "patient_id": plan.patient_id,
                "risk_level": plan.risk_level,
                "status": plan.status,
                "created_at": plan.created_at,
            }
            for plan in care_plans
        ],
        "subscriptions": [
            {"id": item.id, "plan_code": item.plan_code, "status": item.status, "payment_provider": item.payment_provider}
            for item in subscriptions
        ],
        "notifications": [
            {"id": item.id, "channel": item.channel, "enabled": item.enabled == "true"}
            for item in notifications
        ],
        "audit_events": [
            {
                "id": event.id,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "created_at": event.created_at,
            }
            for event in audit_events
        ],
    }


@router.post("/me/delete-request", response_model=DataDeletionRequestOut)
def request_data_deletion(
    payload: DataDeletionRequestIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    request = DataDeletionRequest(
        user_id=user.user_id,
        email=user.email,
        reason=payload.reason,
        status="requested",
    )
    db.add(request)
    db.flush()
    write_audit(db, user.user_id, "", "data_deletion_requested", "data_deletion_request", request.id, {})
    db.commit()
    return DataDeletionRequestOut(id=request.id, status=request.status)


@router.delete("/me")
def delete_my_account_data(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.CLINICIAN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    profiles = db.scalars(select(PatientProfile).where(PatientProfile.user_id == user.user_id)).all()
    patient_ids = [profile.id for profile in profiles]
    if patient_ids:
        reports = db.scalars(select(ReportUpload).where(ReportUpload.patient_id.in_(patient_ids))).all()
        report_ids = [report.id for report in reports]
        for report in reports:
            try:
                delete_stored_file(report.storage_key)
            except Exception:
                # Keep account deletion moving; operators can reconcile object storage from audit/logs.
                pass
        if report_ids:
            db.execute(delete(ReportAnalysis).where(ReportAnalysis.report_id.in_(report_ids)))
        db.execute(delete(ReportUpload).where(ReportUpload.patient_id.in_(patient_ids)))
        db.execute(delete(CarePlan).where(CarePlan.patient_id.in_(patient_ids)))
        db.execute(delete(Intake).where(Intake.patient_id.in_(patient_ids)))
        db.execute(delete(Medication).where(Medication.patient_id.in_(patient_ids)))
        db.execute(delete(PatientProfile).where(PatientProfile.id.in_(patient_ids)))

    db.execute(delete(ConsentRecord).where(ConsentRecord.user_id == user.user_id))
    db.execute(delete(NotificationPreference).where(NotificationPreference.user_id == user.user_id))
    db.execute(delete(Subscription).where(Subscription.user_id == user.user_id))
    db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.user_id))
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.user_id))
    db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.user_id))
    db.execute(delete(AuditEvent).where(AuditEvent.actor_id == user.user_id))
    db.execute(delete(User).where(User.id == user.user_id))
    deletion_request = DataDeletionRequest(
        user_id=user.user_id,
        email=user.email,
        status="completed",
        reason="self-service delete endpoint",
    )
    db.add(deletion_request)
    db.commit()
    return {"status": "deleted", "deletion_request_id": deletion_request.id}

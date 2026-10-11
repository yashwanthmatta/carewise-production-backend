import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.carewise import (
    AuditEvent,
    Clinic,
    ClinicInvite,
    DoctorShare,
    EmailVerificationToken,
    LabPacket,
    PasswordResetToken,
    ReminderEvent,
)
from app.services.audit import write_audit
from app.services.cron_auth import require_cron_token
from app.services.storage import delete_stored_file

# Nightly cleanup run by the scheduler. Deletes what clinics and families should no
# longer have stored: DocBridge labs past the clinic's retention period, expired doctor
# links, old reminder history and used-up sign-in tokens. Audit entries are kept, but
# they never hold lab values.
router = APIRouter()

REMINDER_HISTORY_DAYS = 90
SHARE_GRACE_DAYS = 30
TOKEN_GRACE_DAYS = 1


def run_purge(db: Session, now: datetime) -> dict:
    counts = {"lab_packets": 0, "doctor_shares": 0, "reminder_events": 0, "invites": 0, "tokens": 0}
    for clinic in db.scalars(select(Clinic)).all():
        cutoff = now - timedelta(days=clinic.retention_days or 90)
        old_ids = list(db.scalars(select(LabPacket.id).where(LabPacket.clinic_id == clinic.id, LabPacket.created_at < cutoff)))
        if not old_ids:
            continue
        # Older audit entries may predate the clinic tag; add it so the clinic's log still finds them.
        for event in db.scalars(
            select(AuditEvent).where(AuditEvent.resource_type == "lab_packet", AuditEvent.resource_id.in_(old_ids))
        ):
            data = json.loads(event.metadata_json or "{}")
            if data.get("clinic_id") != clinic.id:
                data["clinic_id"] = clinic.id
                event.metadata_json = json.dumps(data)
        for key in db.scalars(select(LabPacket.file_key).where(LabPacket.id.in_(old_ids), LabPacket.file_key != "")):
            delete_stored_file(key)
        db.execute(delete(LabPacket).where(LabPacket.id.in_(old_ids)))
        write_audit(db, "system", "", "retention_purge", "clinic", clinic.id, {"lab_packets": len(old_ids)})
        counts["lab_packets"] += len(old_ids)
    counts["doctor_shares"] = db.execute(
        delete(DoctorShare).where(DoctorShare.expires_at < now - timedelta(days=SHARE_GRACE_DAYS))
    ).rowcount or 0
    counts["reminder_events"] = db.execute(
        delete(ReminderEvent).where(ReminderEvent.due_at < now - timedelta(days=REMINDER_HISTORY_DAYS))
    ).rowcount or 0
    counts["invites"] = db.execute(delete(ClinicInvite).where(ClinicInvite.expires_at < now)).rowcount or 0
    token_cutoff = now - timedelta(days=TOKEN_GRACE_DAYS)
    counts["tokens"] = (db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at < token_cutoff)).rowcount or 0) + (
        db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.expires_at < token_cutoff)).rowcount or 0
    )
    db.commit()
    return counts


@router.post("/purge", dependencies=[Depends(require_cron_token)])
def purge(db: Session = Depends(get_db)):
    return run_purge(db, datetime.now(timezone.utc))




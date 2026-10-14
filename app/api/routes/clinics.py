import csv
import hashlib
import logging
import io
import json
import secrets
import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_field, encrypt_field
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.carewise import AuditEvent, Clinic, ClinicInvite, ClinicMember, DraftEdit, LabPacket, PatientQuestion
from app.schemas.carewise import (
    ClinicIn,
    ClinicInviteIn,
    ClinicJoinIn,
    ClinicMemberRoleIn,
    ClinicSettingsIn,
    ClinicOut,
    LabPacketApprovedOut,
    LabPacketEditIn,
    LabPacketIn,
    LabPacketOut,
    PacketViewIn,
    PatientQuestionIn,
)
from app.services.audit import write_audit
from app.services.deidentify import deidentify_text, year_only
from app.services.draft_edits import record_draft_edit
from app.services import patient_qa
from app.services.rate_limit import check_rate_limit

# DocBridge: a clinic uploads a lab, FollowThrough Health drafts the patient explanation on the
# clinician's device, a named clinician approves or edits it, and only then does the
# patient get a private link. Nothing is sent without approval; every step is logged.
router = APIRouter()

PATIENT_LINK_DAYS = 30
INVITE_DAYS = 7
APPROVER_ROLES = {"owner", "clinician"}
CLOSED_STATUSES = {"approved", "rejected"}
NOT_AVAILABLE = "This link has expired or is not available. Please contact your clinic."


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ref_hash(clinic_id: str, patient_ref: str) -> str:
    return sha(f"{clinic_id}:{patient_ref.strip().lower()}")


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def load_json(value: str, fallback):
    try:
        data = json.loads(decrypt_field(value)) if value else fallback
    except json.JSONDecodeError:
        return fallback
    return data if isinstance(data, type(fallback)) else fallback


def membership(db: Session, user: CurrentUser, clinic_id: str) -> tuple[Clinic, ClinicMember]:
    member = db.scalar(select(ClinicMember).where(ClinicMember.clinic_id == clinic_id, ClinicMember.user_id == user.user_id))
    clinic = db.get(Clinic, clinic_id)
    if member is None or clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found.")
    return clinic, member


def clinic_packet(db: Session, clinic_id: str, packet_id: str) -> LabPacket:
    packet = db.get(LabPacket, packet_id)
    if packet is None or packet.clinic_id != clinic_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab packet not found.")
    return packet


def packet_out(packet: LabPacket) -> dict:
    return {
        "id": packet.id,
        "patient_ref": decrypt_field(packet.encrypted_patient_ref),
        "lab_date": packet.lab_date,
        "markers": load_json(packet.encrypted_markers, []),
        "summary": decrypt_field(packet.encrypted_summary),
        "questions": load_json(packet.encrypted_questions, []),
        "status": packet.status,
        "approved_by_name": packet.approved_by_name,
        "approved_at": as_utc(packet.approved_at),
        "review_seconds": packet.review_seconds,
        "patient_viewed": packet.patient_viewed_at is not None,
        "edited": None if packet.edited is None else bool(packet.edited),
        "source": packet.source or "manual",
        "created_at": packet.created_at,
    }


def require_approver(member: ClinicMember) -> None:
    if member.role not in APPROVER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a clinician can approve or reject.")


def intake_address(clinic: Clinic) -> str:
    domain = settings.clean_env_value(settings.inbound_email_domain)
    return f"labs+{clinic.intake_code}@{domain}" if domain and clinic.intake_code else ""


def ensure_intake_code(clinic: Clinic) -> None:
    if not clinic.intake_code:
        clinic.intake_code = secrets.token_hex(6)


def clinic_out(clinic: Clinic, member: ClinicMember) -> dict:
    return {
        "intake_address": intake_address(clinic),
        "id": clinic.id,
        "name": clinic.name,
        "tone": clinic.tone,
        "retention_days": clinic.retention_days,
        "clinician_name": member.display_name,
        "member_role": member.role,
        "patient_qa_enabled": bool(clinic.patient_qa_enabled),
    }


@router.post("", response_model=ClinicOut)
def create_clinic(payload: ClinicIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.scalar(select(ClinicMember).where(ClinicMember.user_id == user.user_id)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account already belongs to a clinic.")
    clinic = Clinic(name=payload.name.strip(), tone=payload.tone, owner_user_id=user.user_id, retention_days=90)
    ensure_intake_code(clinic)
    db.add(clinic)
    db.flush()
    member = ClinicMember(clinic_id=clinic.id, user_id=user.user_id, display_name=payload.clinician_name.strip(), role="owner")
    db.add(member)
    write_audit(db, user.user_id, "", "clinic_created", "clinic", clinic.id, {})
    db.commit()
    return clinic_out(clinic, member)


@router.get("/me", response_model=ClinicOut)
def my_clinic(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    member = db.scalar(select(ClinicMember).where(ClinicMember.user_id == user.user_id))
    clinic = db.get(Clinic, member.clinic_id) if member else None
    if member is None or clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No clinic yet.")
    if not clinic.intake_code:
        ensure_intake_code(clinic)
        db.commit()
    return clinic_out(clinic, member)


@router.post("/{clinic_id}/packets", response_model=LabPacketOut)
def create_packet(
    clinic_id: str,
    payload: LabPacketIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership(db, user, clinic_id)
    # Pilot mode: until the clinic's BAA is signed, only de-identified or sample labs.
    if not payload.deidentified_confirmed:
        raise HTTPException(status_code=422, detail="Confirm the lab is de-identified or a sample during the pilot.")
    packet = LabPacket(
        clinic_id=clinic_id,
        patient_ref_hash=ref_hash(clinic_id, payload.patient_ref),
        encrypted_patient_ref=encrypt_field(payload.patient_ref.strip()),
        lab_date=payload.lab_date,
        encrypted_markers=encrypt_field(json.dumps([marker.model_dump() for marker in payload.markers])),
        encrypted_summary=encrypt_field(payload.summary.strip()),
        encrypted_draft=encrypt_field(payload.summary.strip()),
        encrypted_questions=encrypt_field(json.dumps([q.strip() for q in payload.questions if q.strip()])),
        encrypted_draft_questions=encrypt_field(json.dumps([q.strip() for q in payload.questions if q.strip()])),
        model_version=payload.model_version,
        prompt_version=payload.prompt_version,
        # Nothing could be read: a person types the values in, never a guess.
        status="draft" if payload.markers else "manual_review",
        created_by=user.user_id,
    )
    db.add(packet)
    db.flush()
    write_audit(db, user.user_id, "", "packet_drafted", "lab_packet", packet.id, {"markers": len(payload.markers), "clinic_id": clinic_id})
    db.commit()
    db.refresh(packet)
    return packet_out(packet)


@router.get("/{clinic_id}/packets", response_model=list[LabPacketOut])
def list_packets(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    clinic, _ = membership(db, user, clinic_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=clinic.retention_days or 90)
    packets = db.scalars(
        select(LabPacket).where(LabPacket.clinic_id == clinic_id).order_by(LabPacket.created_at.desc()).limit(200)
    ).all()
    return [packet_out(p) for p in packets if (as_utc(p.created_at) or cutoff) >= cutoff]


@router.put("/{clinic_id}/packets/{packet_id}", response_model=LabPacketOut)
def edit_packet(
    clinic_id: str,
    packet_id: str,
    payload: LabPacketEditIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership(db, user, clinic_id)
    packet = clinic_packet(db, clinic_id, packet_id)
    if packet.status in CLOSED_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved or rejected packets can't be edited.")
    first_draft = packet.status == "new"
    if payload.markers is not None and (first_draft or not packet.encrypted_markers):
        packet.encrypted_markers = encrypt_field(json.dumps([m.model_dump() for m in payload.markers]))
    if payload.lab_date is not None and not packet.lab_date:
        packet.lab_date = payload.lab_date
    packet.encrypted_summary = encrypt_field(payload.summary.strip())
    packet.encrypted_questions = encrypt_field(json.dumps([q.strip() for q in payload.questions if q.strip()]))
    if first_draft:
        # The first draft of an emailed lab, made on the clinician's screen; approval
        # later compares against it to record whether the clinician edited it.
        packet.status = "draft" if payload.markers else "manual_review"
        packet.encrypted_draft = packet.encrypted_summary
        packet.encrypted_draft_questions = packet.encrypted_questions
        packet.model_version = payload.model_version or packet.model_version
        packet.prompt_version = payload.prompt_version or packet.prompt_version
    else:
        record_draft_edit(db, packet, user.user_id, payload.summary, payload.questions, approved=False)
    write_audit(db, user.user_id, "", "packet_drafted" if first_draft else "packet_edited", "lab_packet", packet.id, {"clinic_id": clinic_id})
    db.commit()
    db.refresh(packet)
    return packet_out(packet)


@router.post("/{clinic_id}/packets/{packet_id}/approve", response_model=LabPacketApprovedOut)
def approve_packet(
    clinic_id: str,
    packet_id: str,
    payload: LabPacketEditIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, member = membership(db, user, clinic_id)
    require_approver(member)
    packet = clinic_packet(db, clinic_id, packet_id)
    if packet.status in CLOSED_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already approved or rejected.")
    if not payload.summary.strip():
        raise HTTPException(status_code=422, detail="Add the patient explanation before approving.")
    if packet.status == "new":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Open the emailed lab to draft it before approving.")
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    packet.edited = int(payload.summary.strip() != decrypt_field(packet.encrypted_draft).strip())
    edit = record_draft_edit(db, packet, user.user_id, payload.summary, payload.questions, approved=True)
    packet.encrypted_summary = encrypt_field(payload.summary.strip())
    packet.encrypted_questions = encrypt_field(json.dumps([q.strip() for q in payload.questions if q.strip()]))
    packet.status = "approved"
    packet.approved_by = user.user_id
    packet.approved_by_name = member.display_name
    packet.approved_at = now
    packet.review_seconds = max(0, int((now - (as_utc(packet.created_at) or now)).total_seconds()))
    packet.patient_token_hash = sha(token)
    packet.expires_at = now + timedelta(days=PATIENT_LINK_DAYS)
    write_audit(
        db, user.user_id, "", "packet_approved", "lab_packet", packet.id,
        {"review_seconds": packet.review_seconds, "edited": bool(packet.edited), "edit_distance": edit.edit_distance, "by": member.display_name, "clinic_id": clinic_id},
    )
    db.commit()
    db.refresh(packet)
    return {**packet_out(packet), "patient_token": token}


@router.post("/{clinic_id}/packets/{packet_id}/follow-up", response_model=LabPacketOut)
def mark_follow_up(clinic_id: str, packet_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, clinic_id)
    packet = clinic_packet(db, clinic_id, packet_id)
    if packet.status not in CLOSED_STATUSES:
        packet.status = "needs_call"
    write_audit(db, user.user_id, "", "packet_needs_call", "lab_packet", packet.id, {"clinic_id": clinic_id})
    db.commit()
    db.refresh(packet)
    return packet_out(packet)


@router.post("/{clinic_id}/packets/{packet_id}/reject", response_model=LabPacketOut)
def reject_packet(clinic_id: str, packet_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _, member = membership(db, user, clinic_id)
    require_approver(member)
    packet = clinic_packet(db, clinic_id, packet_id)
    if packet.status == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved packets can't be rejected.")
    packet.status = "rejected"
    write_audit(db, user.user_id, "", "packet_rejected", "lab_packet", packet.id, {"by": member.display_name, "clinic_id": clinic_id})
    db.commit()
    db.refresh(packet)
    return packet_out(packet)


@router.get("/{clinic_id}/packets/{packet_id}/source")
def packet_source(clinic_id: str, packet_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # The text read from an emailed lab PDF, so the clinician's screen can run the lab parser.
    membership(db, user, clinic_id)
    packet = clinic_packet(db, clinic_id, packet_id)
    return {"text": decrypt_field(packet.encrypted_source_text) if packet.encrypted_source_text else ""}


ACTION_LABELS = {
    "packet_drafted": "Draft created",
    "packet_edited": "Draft edited",
    "packet_approved": "Approved and patient link created",
    "packet_needs_call": "Marked as needs a follow-up call",
    "packet_rejected": "Rejected, not sent",
    "packet_viewed_by_patient": "Opened by the patient",
    "packet_received_by_email": "Received by email",
    "intake_rejected_sender": "Email ignored: sender not on the team",
    "intake_rejected_not_deidentified": "Email ignored: DEID missing from subject",
    "intake_no_pdf": "Email ignored: no PDF attached",
    "clinic_created": "Clinic created",
    "clinic_settings_changed": "Clinic settings changed",
    "clinic_invite_created": "Invite code created",
    "clinic_joined": "Joined the clinic",
    "clinic_member_role_changed": "Team member role changed",
    "clinic_member_removed": "Team member removed",
    "clinic_member_left": "Left the clinic",
    "visit_summary_viewed": "Visit summary opened",
    "training_export": "De-identified edit pairs downloaded",
    "patient_questions_reviewed": "Patient questions reviewed",
    "audit_exported": "Audit log downloaded",
    "retention_purge": "Old labs deleted (retention)",
}
RETENTION_CHOICES = {30, 60, 90, 180, 365}


@router.get("/{clinic_id}/packets/{packet_id}/audit")
def packet_audit(clinic_id: str, packet_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, clinic_id)
    clinic_packet(db, clinic_id, packet_id)
    names = {m.user_id: m.display_name for m in db.scalars(select(ClinicMember).where(ClinicMember.clinic_id == clinic_id))}
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.resource_type == "lab_packet", AuditEvent.resource_id == packet_id).order_by(AuditEvent.created_at)
    ).all()
    return [
        {
            "action": ACTION_LABELS.get(event.action, event.action),
            "who": "Patient" if event.actor_id == "patient_link" else names.get(event.actor_id, "Former team member"),
            "at": as_utc(event.created_at),
        }
        for event in events
    ]


@router.put("/{clinic_id}/settings", response_model=ClinicOut)
def update_settings(
    clinic_id: str, payload: ClinicSettingsIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    clinic, member = membership(db, user, clinic_id)
    if member.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the clinic owner can change settings.")
    if payload.retention_days not in RETENTION_CHOICES:
        raise HTTPException(status_code=422, detail="Choose 30, 60, 90, 180 or 365 days.")
    changes = {
        key: value
        for key, value in (("name", payload.name.strip()), ("tone", payload.tone), ("retention_days", payload.retention_days))
        if getattr(clinic, key) != value
    }
    if payload.patient_qa_enabled is not None and bool(clinic.patient_qa_enabled) != payload.patient_qa_enabled:
        changes["patient_qa_enabled"] = int(payload.patient_qa_enabled)
    for key, value in changes.items():
        setattr(clinic, key, value)
    if changes:
        write_audit(db, user.user_id, "", "clinic_settings_changed", "clinic", clinic_id, {k: v for k, v in changes.items() if k != "name"})
    db.commit()
    return clinic_out(clinic, member)


# The clinic's full activity log as a spreadsheet, for its own compliance records.
# It lists who did what and when; it never includes lab values or explanations.
@router.get("/{clinic_id}/audit.csv")
def export_audit(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    clinic, member = membership(db, user, clinic_id)
    if member.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the clinic owner can download the log.")
    write_audit(db, user.user_id, "", "audit_exported", "clinic", clinic_id, {})
    db.commit()
    names = {m.user_id: m.display_name for m in db.scalars(select(ClinicMember).where(ClinicMember.clinic_id == clinic_id))}
    packet_ids = list(db.scalars(select(LabPacket.id).where(LabPacket.clinic_id == clinic_id)))
    tag = f'"clinic_id": "{clinic_id}"'
    events = db.scalars(
        select(AuditEvent)
        .where(
            or_(
                (AuditEvent.resource_type == "clinic") & (AuditEvent.resource_id == clinic_id),
                (AuditEvent.resource_type == "lab_packet") & AuditEvent.resource_id.in_(packet_ids or [""]),
                (AuditEvent.resource_type == "lab_packet") & AuditEvent.metadata_json.contains(tag),
            )
        )
        .order_by(AuditEvent.created_at)
    ).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["When (UTC)", "Who", "What", "Record"])
    for event in events:
        who = "Patient" if event.actor_id == "patient_link" else "FollowThrough Health (automatic)" if event.actor_id == "system" else names.get(event.actor_id, "Former team member")
        record = f"Lab {event.resource_id[-8:]}" if event.resource_type == "lab_packet" else "Clinic"
        when = (as_utc(event.created_at) or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M")
        writer.writerow([when, who, ACTION_LABELS.get(event.action, event.action), record])
    safe = "".join(ch for ch in clinic.name if ch.isalnum() or ch in " -")[:40].strip().replace(" ", "-") or "clinic"
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe}-docbridge-audit.csv"'},
    )


@router.post("/{clinic_id}/invites")
def create_invite(clinic_id: str, payload: ClinicInviteIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _, member = membership(db, user, clinic_id)
    if member.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the clinic owner can invite people.")
    code = secrets.token_urlsafe(9)
    expires = datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS)
    db.add(ClinicInvite(clinic_id=clinic_id, code_hash=sha(code), role=payload.role, expires_at=expires))
    write_audit(db, user.user_id, "", "clinic_invite_created", "clinic", clinic_id, {"role": payload.role})
    db.commit()
    return {"code": code, "role": payload.role, "expires_at": expires}


@router.post("/join", response_model=ClinicOut)
def join_clinic(payload: ClinicJoinIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.scalar(select(ClinicMember).where(ClinicMember.user_id == user.user_id)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account already belongs to a clinic.")
    invite = db.scalar(select(ClinicInvite).where(ClinicInvite.code_hash == sha(payload.code.strip())))
    now = datetime.now(timezone.utc)
    if invite is None or invite.used_at is not None or (as_utc(invite.expires_at) or now) <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invite code is not valid. Ask for a new one.")
    clinic = db.get(Clinic, invite.clinic_id)
    member = ClinicMember(clinic_id=invite.clinic_id, user_id=user.user_id, display_name=payload.display_name.strip(), role=invite.role)
    invite.used_at = now
    db.add(member)
    write_audit(db, user.user_id, "", "clinic_joined", "clinic", invite.clinic_id, {"role": invite.role})
    db.commit()
    return clinic_out(clinic, member)


@router.get("/{clinic_id}/members")
def list_members(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, clinic_id)
    members = db.scalars(select(ClinicMember).where(ClinicMember.clinic_id == clinic_id).order_by(ClinicMember.created_at)).all()
    return [{"id": m.id, "name": m.display_name, "role": m.role, "you": m.user_id == user.user_id} for m in members]


def owner_and_target(db: Session, user: CurrentUser, clinic_id: str, member_id: str) -> ClinicMember:
    _, me = membership(db, user, clinic_id)
    if me.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the clinic owner can manage the team.")
    target = db.get(ClinicMember, member_id)
    if target is None or target.clinic_id != clinic_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found.")
    if target.id == me.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The owner's own role can't be changed here.")
    return target


# The owner changes what a team member may do (approve as a clinician, or prepare
# drafts only at the front desk), or removes them. Their past steps stay in the audit trail.
@router.put("/{clinic_id}/members/{member_id}")
def change_member_role(
    clinic_id: str, member_id: str, payload: ClinicMemberRoleIn,
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db),
):
    target = owner_and_target(db, user, clinic_id, member_id)
    previous = target.role
    target.role = payload.role
    write_audit(db, user.user_id, "", "clinic_member_role_changed", "clinic", clinic_id, {"from": previous, "to": payload.role})
    db.commit()
    return {"id": target.id, "name": target.display_name, "role": target.role, "you": False}


@router.delete("/{clinic_id}/members/{member_id}")
def remove_member(clinic_id: str, member_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    target = owner_and_target(db, user, clinic_id, member_id)
    db.delete(target)
    write_audit(db, user.user_id, "", "clinic_member_removed", "clinic", clinic_id, {"role": target.role})
    db.commit()
    return {"status": "removed"}


@router.post("/{clinic_id}/leave")
def leave_clinic(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    _, me = membership(db, user, clinic_id)
    if me.role == "owner":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The owner can't leave the clinic.")
    db.delete(me)
    write_audit(db, user.user_id, "", "clinic_member_left", "clinic", clinic_id, {"role": me.role})
    db.commit()
    return {"status": "left"}


# Visit-ready summary: every packet for one patient, with what changed between labs.
@router.get("/{clinic_id}/patients/{patient_ref}/summary")
def visit_summary(clinic_id: str, patient_ref: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, clinic_id)
    packets = db.scalars(
        select(LabPacket).where(LabPacket.clinic_id == clinic_id, LabPacket.patient_ref_hash == ref_hash(clinic_id, patient_ref))
    ).all()
    packets = sorted(packets, key=lambda p: (p.lab_date or "", as_utc(p.created_at) or datetime.min.replace(tzinfo=timezone.utc)))
    history = [packet_out(p) for p in packets]
    changes = []
    if len(history) >= 2:
        before = {m["name"]: m for m in history[-2]["markers"]}
        for marker in history[-1]["markers"]:
            old = before.get(marker["name"])
            if old and old.get("value") != marker.get("value"):
                changes.append({"name": marker["name"], "before": old.get("value"), "now": marker.get("value"), "unit": marker.get("unit", ""), "status": marker.get("status", "")})
    write_audit(db, user.user_id, "", "visit_summary_viewed", "clinic", clinic_id, {"packets": len(history)})
    db.commit()
    return {"patient_ref": patient_ref, "packets": history, "changes": changes}


@router.get("/{clinic_id}/metrics")
def clinic_metrics(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, clinic_id)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    packets = db.scalars(select(LabPacket).where(LabPacket.clinic_id == clinic_id)).all()
    approved = [p for p in packets if p.status == "approved"]
    this_week = [p for p in approved if (as_utc(p.approved_at) or week_ago) > week_ago]
    reviews = [p.review_seconds for p in approved if p.review_seconds is not None]
    return {
        "drafts": sum(1 for p in packets if p.status == "draft"),
        "manual_review": sum(1 for p in packets if p.status == "manual_review"),
        "needs_call": sum(1 for p in packets if p.status == "needs_call"),
        "approved_this_week": len(this_week),
        "median_review_seconds": int(statistics.median(reviews)) if reviews else None,
        "patients_opened": sum(1 for p in approved if p.patient_viewed_at is not None),
        "approved_without_edits": sum(1 for p in approved if p.edited == 0),
    }


@router.get("/{clinic_id}/edit-metrics")
def edit_metrics(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # How much doctors change drafts, per draft generator and week. Lower edit distance
    # and more approvals without edits mean the drafts are getting closer to what
    # doctors want.
    membership(db, user, clinic_id)
    edits = db.scalars(select(DraftEdit).where(DraftEdit.clinic_id == clinic_id)).all()
    groups: dict[tuple[str, str], list[DraftEdit]] = {}
    for edit in edits:
        created = as_utc(edit.created_at) or datetime.now(timezone.utc)
        year, week, _ = created.isocalendar()
        groups.setdefault((edit.model_version, f"{year}-W{week:02d}"), []).append(edit)
    rows = []
    for (version, week), items in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        approvals = [e for e in items if e.event == "approve"]
        zero = sum(e.zero_edit_approval for e in approvals)
        rows.append({
            "model_version": version,
            "week": week,
            "approvals": len(approvals),
            "approval_without_edit_rate": round(zero / len(approvals), 3) if approvals else None,
            "mean_edit_distance": round(statistics.mean(e.edit_distance for e in approvals), 1) if approvals else None,
            "saves": len(items) - len(approvals),
        })
    return {"weeks": rows, "pairs_collected_total": sum(1 for e in edits if e.edit_distance > 0), "edits_recorded_total": len(edits)}


@router.get("/{clinic_id}/training-pairs.jsonl")
def training_pairs_export(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # Owner only. De-identified (original draft, doctor's version) pairs for prompt
    # review and, once a BAA is in place, fine-tuning. Lab values stay; identifiers go.
    clinic, member = membership(db, user, clinic_id)
    if member.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the clinic owner can download training pairs.")
    packets = {p.id: p for p in db.scalars(select(LabPacket).where(LabPacket.clinic_id == clinic_id))}
    names = [clinic.name] + [m.display_name for m in db.scalars(select(ClinicMember).where(ClinicMember.clinic_id == clinic_id))]
    lines = []
    for edit in db.scalars(select(DraftEdit).where(DraftEdit.clinic_id == clinic_id).order_by(DraftEdit.created_at)):
        packet = packets.get(edit.packet_id)
        if packet is None:
            continue
        known = names + [decrypt_field(packet.encrypted_patient_ref)]
        markers = [
            {k: deidentify_text(str(m.get(k, "")), known) for k in ("name", "value", "unit", "range", "status")}
            for m in load_json(packet.encrypted_markers, [])
        ]
        original = deidentify_text(decrypt_field(edit.encrypted_original_text), known)
        edited = deidentify_text(decrypt_field(edit.encrypted_edited_text), known)
        lines.append(json.dumps({
            "prompt": {"lab_year": year_only(packet.lab_date), "markers": markers, "tone": clinic.tone or "friendly"},
            "chosen": edited,
            "rejected": original,
            "event": edit.event,
            "zero_edit_approval": bool(edit.zero_edit_approval),
            "edited_sections": json.loads(edit.edited_sections or "{}"),
            "edit_distance": edit.edit_distance,
            "model_version": edit.model_version,
            "prompt_version": edit.prompt_version,
            "week": "{}-W{:02d}".format(*(as_utc(edit.created_at) or datetime.now(timezone.utc)).isocalendar()[:2]),
        }))
    write_audit(db, user.user_id, "", "training_export", "clinic", clinic_id, {"pairs": len(lines), "clinic_id": clinic_id})
    db.commit()
    return Response(
        content="\n".join(lines) + ("\n" if lines else ""),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="docbridge-training-pairs.jsonl"', "Cache-Control": "no-store"},
    )


# Patient side: the approved explanation, opened from the private link. No account.
@router.post("/packets/view")
def view_packet(payload: PacketViewIn, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(db, request, "packet_view", max_attempts=60, window_seconds=3600)
    packet = db.scalar(select(LabPacket).where(LabPacket.patient_token_hash == sha(payload.token)))
    now = datetime.now(timezone.utc)
    if packet is None or packet.status != "approved" or (as_utc(packet.expires_at) or now) <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_AVAILABLE)
    clinic = db.get(Clinic, packet.clinic_id)
    if packet.patient_viewed_at is None:
        packet.patient_viewed_at = now
    write_audit(db, "patient_link", "", "packet_viewed_by_patient", "lab_packet", packet.id, {"clinic_id": packet.clinic_id})
    db.commit()
    data = packet_out(packet)
    return {
        "clinic_name": clinic.name if clinic else "",
        "approved_by_name": data["approved_by_name"],
        "approved_at": data["approved_at"],
        "lab_date": data["lab_date"],
        "markers": data["markers"],
        "summary": data["summary"],
        "questions": data["questions"],
        "questions_enabled": bool(clinic and clinic.patient_qa_enabled),
    }


QA_PER_PACKET_PER_DAY = 30
qa_log = logging.getLogger("carewise.patient_qa")


def open_patient_packet(db: Session, token: str) -> LabPacket:
    packet = db.scalar(select(LabPacket).where(LabPacket.patient_token_hash == sha(token)))
    now = datetime.now(timezone.utc)
    if packet is None or packet.status != "approved" or (as_utc(packet.expires_at) or now) <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_AVAILABLE)
    return packet


@router.post("/packets/qa")
def patient_question(payload: PatientQuestionIn, request: Request, db: Session = Depends(get_db)):
    # The private link is the only key: answers use this packet's approved summary and
    # values plus this patient's earlier approved labs at the same clinic, nothing else.
    from app.api.routes import assistant

    check_rate_limit(db, request, "patient_qa", max_attempts=20, window_seconds=3600)
    packet = open_patient_packet(db, payload.token)
    clinic = db.get(Clinic, packet.clinic_id)
    if clinic is None or not clinic.patient_qa_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your clinic hasn't turned on questions. Please ask your care team.")
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    asked_today = len(db.scalars(select(PatientQuestion.id).where(PatientQuestion.packet_id == packet.id, PatientQuestion.created_at >= day_ago)).all())
    if asked_today >= QA_PER_PACKET_PER_DAY:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="That's a lot of questions for one day. Please bring the rest to your care team.")
    question = payload.question.strip()
    reason = patient_qa.screen_question(question)
    model = ""
    if reason:
        result = patient_qa.deflection(reason)
    elif not assistant.assistant_enabled():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Questions aren't switched on yet. Please ask your care team.")
    else:
        older = db.scalars(
            select(LabPacket).where(
                LabPacket.clinic_id == packet.clinic_id,
                LabPacket.patient_ref_hash == packet.patient_ref_hash,
                LabPacket.status == "approved",
                LabPacket.id != packet.id,
            ).order_by(LabPacket.approved_at.desc()).limit(5)
        ).all()
        sources = patient_qa.build_sources(
            decrypt_field(packet.encrypted_summary),
            load_json(packet.encrypted_markers, []),
            packet.lab_date,
            [(p.lab_date, load_json(p.encrypted_markers, [])) for p in older],
        )
        try:
            response = assistant.get_client().beta.messages.create(
                model=settings.assistant_model,
                max_tokens=1500,
                system=patient_qa.SYSTEM_PROMPT,
                # Names, birth dates and contact details the patient types are removed first.
                messages=[{"role": "user", "content": patient_qa.user_message(deidentify_text(question), sources)}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except Exception as exc:  # noqa: BLE001 - any provider failure gets the same polite reply
            qa_log.warning("patient question failed: %s", type(exc).__name__)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We couldn't answer right now. Please try again, or ask your care team.") from exc
        model = getattr(response, "model", "") or ""
        if getattr(response, "stop_reason", "") == "refusal":
            result = patient_qa.deflection("outside")
        else:
            raw = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
            result = patient_qa.parse_answer(raw, sources)
            if not result["deflect_to_doctor"]:
                # A second, independent check; any doubt or error means "ask your doctor".
                try:
                    check = assistant.get_client().beta.messages.create(
                        model=settings.assistant_model,
                        max_tokens=200,
                        system=patient_qa.SAFETY_PROMPT,
                        messages=[{"role": "user", "content": patient_qa.safety_message(result["answer"], sources)}],
                        output_config={"effort": "low"},
                        betas=["server-side-fallback-2026-07-01"],
                        fallbacks="default",
                    )
                    verdict = "".join(block.text for block in check.content if getattr(block, "type", "") == "text")
                    safe = getattr(check, "stop_reason", "") != "refusal" and patient_qa.passed_safety_check(verdict)
                except Exception as exc:  # noqa: BLE001 - fail closed
                    qa_log.warning("patient answer check failed: %s", type(exc).__name__)
                    safe = False
                if not safe:
                    result = {**patient_qa.deflection("outside"), "reason": "failed_check"}
    db.add(PatientQuestion(
        packet_id=packet.id,
        clinic_id=packet.clinic_id,
        encrypted_question=encrypt_field(question),
        encrypted_answer=encrypt_field(result["answer"]),
        citations=json.dumps(result["citations"]),
        deflected=int(result["deflect_to_doctor"]),
        reason=result["reason"],
        model=model[:80],
    ))
    db.commit()
    return {"answer": result["answer"], "citations": result["citations"], "deflect_to_doctor": result["deflect_to_doctor"]}


@router.get("/{clinic_id}/patient-questions")
def patient_questions_log(clinic_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    # Owner safety review: what patients asked and what they were told.
    _, member = membership(db, user, clinic_id)
    if member.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the clinic owner can review patient questions.")
    refs = {p.id: decrypt_field(p.encrypted_patient_ref) for p in db.scalars(select(LabPacket).where(LabPacket.clinic_id == clinic_id))}
    rows = db.scalars(
        select(PatientQuestion).where(PatientQuestion.clinic_id == clinic_id).order_by(PatientQuestion.created_at.desc()).limit(200)
    ).all()
    write_audit(db, user.user_id, "", "patient_questions_reviewed", "clinic", clinic_id, {"rows": len(rows), "clinic_id": clinic_id})
    db.commit()
    return [
        {
            "patient_ref": refs.get(r.packet_id, ""),
            "question": decrypt_field(r.encrypted_question),
            "answer": decrypt_field(r.encrypted_answer),
            "citations": json.loads(r.citations or "[]"),
            "deflected": bool(r.deflected),
            "reason": r.reason,
            "created_at": r.created_at,
        }
        for r in rows
    ]

import hashlib
import json
import secrets
import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_field, encrypt_field
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.carewise import Clinic, ClinicMember, LabPacket
from app.schemas.carewise import (
    ClinicIn,
    ClinicOut,
    LabPacketApprovedOut,
    LabPacketEditIn,
    LabPacketIn,
    LabPacketOut,
    PacketViewIn,
)
from app.services.audit import write_audit
from app.services.rate_limit import check_rate_limit

# DocBridge: a clinic uploads a lab, CareWise drafts the patient explanation on the
# clinician's device, a named clinician approves or edits it, and only then does the
# patient get a private link. Nothing is sent without approval; every step is logged.
router = APIRouter()

PATIENT_LINK_DAYS = 30
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
        "created_at": packet.created_at,
    }


def clinic_out(clinic: Clinic, member: ClinicMember) -> dict:
    return {
        "id": clinic.id,
        "name": clinic.name,
        "tone": clinic.tone,
        "retention_days": clinic.retention_days,
        "clinician_name": member.display_name,
        "member_role": member.role,
    }


@router.post("", response_model=ClinicOut)
def create_clinic(payload: ClinicIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.scalar(select(ClinicMember).where(ClinicMember.user_id == user.user_id)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account already belongs to a clinic.")
    clinic = Clinic(name=payload.name.strip(), tone=payload.tone, owner_user_id=user.user_id, retention_days=90)
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
        encrypted_questions=encrypt_field(json.dumps([q.strip() for q in payload.questions if q.strip()])),
        status="draft",
        created_by=user.user_id,
    )
    db.add(packet)
    db.flush()
    write_audit(db, user.user_id, "", "packet_drafted", "lab_packet", packet.id, {"markers": len(payload.markers)})
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
    if packet.status == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved packets can't be edited.")
    packet.encrypted_summary = encrypt_field(payload.summary.strip())
    packet.encrypted_questions = encrypt_field(json.dumps([q.strip() for q in payload.questions if q.strip()]))
    write_audit(db, user.user_id, "", "packet_edited", "lab_packet", packet.id, {})
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
    packet = clinic_packet(db, clinic_id, packet_id)
    if packet.status == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already approved.")
    if not payload.summary.strip():
        raise HTTPException(status_code=422, detail="Add the patient explanation before approving.")
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    packet.encrypted_summary = encrypt_field(payload.summary.strip())
    packet.encrypted_questions = encrypt_field(json.dumps([q.strip() for q in payload.questions if q.strip()]))
    packet.status = "approved"
    packet.approved_by = user.user_id
    packet.approved_by_name = member.display_name
    packet.approved_at = now
    packet.review_seconds = max(0, int((now - (as_utc(packet.created_at) or now)).total_seconds()))
    packet.patient_token_hash = sha(token)
    packet.expires_at = now + timedelta(days=PATIENT_LINK_DAYS)
    write_audit(db, user.user_id, "", "packet_approved", "lab_packet", packet.id, {"review_seconds": packet.review_seconds})
    db.commit()
    db.refresh(packet)
    return {**packet_out(packet), "patient_token": token}


@router.post("/{clinic_id}/packets/{packet_id}/follow-up", response_model=LabPacketOut)
def mark_follow_up(clinic_id: str, packet_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    membership(db, user, clinic_id)
    packet = clinic_packet(db, clinic_id, packet_id)
    if packet.status != "approved":
        packet.status = "needs_call"
    write_audit(db, user.user_id, "", "packet_needs_call", "lab_packet", packet.id, {})
    db.commit()
    db.refresh(packet)
    return packet_out(packet)


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
        "needs_call": sum(1 for p in packets if p.status == "needs_call"),
        "approved_this_week": len(this_week),
        "median_review_seconds": int(statistics.median(reviews)) if reviews else None,
        "patients_opened": sum(1 for p in approved if p.patient_viewed_at is not None),
    }


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
    write_audit(db, "patient_link", "", "packet_viewed_by_patient", "lab_packet", packet.id, {})
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
    }

import base64
import hmac
import json
import logging
import re
import urllib.parse
import urllib.request
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import encrypt_bytes, encrypt_field
from app.db.session import get_db
from app.models.carewise import Clinic, ClinicMember, LabPacket, User
from app.services.audit import write_audit
from app.services.storage import pdf_bytes_to_text, store_private_bytes

# DocBridge email intake. A clinic team member forwards a lab PDF to the clinic's private
# address (labs+CODE@<inbound domain>). The email provider posts the message here; each
# PDF is encrypted, stored, its text read, and a "new" lab appears in the clinic inbox.
# The lab parser runs later on the clinician's screen, the same one used for uploads.
#
# Pilot safety rules: only mail from an address that belongs to a member of that clinic is
# accepted, and the subject must contain DEID (the sender confirms the lab is
# de-identified). Anything else is dropped without storing the attachment.
router = APIRouter()
log = logging.getLogger(__name__)

MAX_ATTACHMENTS = 5
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_RAW_BYTES = 40 * 1024 * 1024
CODE_PATTERN = re.compile(r"^(?:labs\+)?([a-z0-9]{8,24})$")
SUBJECT_NOISE = re.compile(r"^\s*((fwd?|fw|re)\s*:\s*)+", re.IGNORECASE)


def check_token(token: str) -> None:
    expected = settings.clean_env_value(settings.inbound_email_token)
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")


async def raw_message_from_request(request: Request) -> bytes | None:
    """Accept the common inbound formats: SendGrid Inbound Parse (raw), Amazon SES via SNS,
    a JSON body with base64 "raw", or the raw MIME message itself."""
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        raw = form.get("email")
        if raw is None:
            return None
        return raw.encode("utf-8", "surrogateescape") if isinstance(raw, str) else await raw.read()
    body = await request.body()
    if len(body) > MAX_RAW_BYTES:
        return None
    if "json" in content_type or body[:1] == b"{":
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        if data.get("Type") == "SubscriptionConfirmation":
            confirm_sns_subscription(data.get("SubscribeURL", ""))
            return None
        if data.get("Type") == "Notification":
            data = json.loads(data.get("Message") or "{}")
            content = data.get("content") or ""
            encoding = (data.get("receipt", {}).get("action", {}).get("encoding") or "").upper()
            return base64.b64decode(content) if encoding == "BASE64" else content.encode("utf-8", "surrogateescape")
        if data.get("raw"):
            return base64.b64decode(data["raw"])
        return None
    return body or None


def confirm_sns_subscription(url: str) -> None:
    # Only ever call back to Amazon SNS itself.
    host = urllib.parse.urlparse(url).hostname or ""
    if url.startswith("https://") and re.fullmatch(r"sns\.[a-z0-9-]+\.amazonaws\.com", host):
        try:
            urllib.request.urlopen(url, timeout=10).read()  # noqa: S310 - host checked above
        except Exception:  # noqa: BLE001
            log.warning("SNS subscription confirmation failed")


def recipient_codes(message: EmailMessage) -> list[str]:
    domain = settings.clean_env_value(settings.inbound_email_domain).lower()
    headers = []
    for name in ("To", "Cc", "Delivered-To", "X-Original-To", "X-Forwarded-To"):
        headers.extend(message.get_all(name, []))
    codes = []
    for _, address in getaddresses([str(value) for value in headers]):
        local, _, host = address.lower().partition("@")
        match = CODE_PATTERN.match(local)
        if match and (not domain or host == domain):
            codes.append(match.group(1))
    return codes


# A patient code in the subject must look like one: letters, a dash, then 3+ digits,
# right after DEID ("DEID JD-1042"). Lab names and dates ("A1C", "B12", "CMP-14",
# "10/14") never count, so two patients can't end up under the same code.
EXPLICIT_REF = re.compile(r"^[A-Za-z]{1,6}-\d{3,10}$")
LAB_WORDS = {"cmp", "bmp", "cbc", "lft", "tsh", "a1c", "hba1c", "lipid", "lipids", "panel", "labs", "lab"}


def patient_ref_from(subject: str) -> str | None:
    rest = SUBJECT_NOISE.sub("", subject or "")
    match = re.search(r"\bdeid\b[\s:\-–]*([^\s,;]+)", rest, re.IGNORECASE)
    if not match:
        return None
    word = match.group(1).strip(" :-[]()")
    if not EXPLICIT_REF.match(word) or word.split("-")[0].lower() in LAB_WORDS:
        return None
    return word


def pdf_attachments(message: EmailMessage) -> list[tuple[str, bytes]]:
    files = []
    for part in message.walk():
        name = part.get_filename() or ""
        if part.get_content_type() == "application/pdf" or name.lower().endswith(".pdf"):
            data = part.get_payload(decode=True) or b""
            if data and len(data) <= MAX_PDF_BYTES:
                files.append((name or "lab.pdf", data))
        if len(files) >= MAX_ATTACHMENTS:
            break
    return files


def process_message(db: Session, raw: bytes) -> dict:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    codes = recipient_codes(message)
    clinic = db.scalar(select(Clinic).where(Clinic.intake_code.in_(codes))) if codes else None
    if clinic is None:
        return {"status": "ignored", "reason": "unknown_address"}
    sender = parseaddr(str(message.get("From", "")))[1].strip().lower()
    member = db.scalar(
        select(ClinicMember).join(User, User.id == ClinicMember.user_id).where(ClinicMember.clinic_id == clinic.id, User.email == sender)
    )
    if member is None:
        write_audit(db, "system", "", "intake_rejected_sender", "clinic", clinic.id, {})
        db.commit()
        return {"status": "ignored", "reason": "sender_not_in_clinic"}
    subject = str(message.get("Subject", ""))
    if not re.search(r"\bdeid\b", subject, re.IGNORECASE):
        write_audit(db, member.user_id, "", "intake_rejected_not_deidentified", "clinic", clinic.id, {})
        db.commit()
        return {"status": "ignored", "reason": "missing_deid_confirmation"}
    files = pdf_attachments(message)
    if not files:
        write_audit(db, member.user_id, "", "intake_no_pdf", "clinic", clinic.id, {})
        db.commit()
        return {"status": "ignored", "reason": "no_pdf"}
    patient_ref = patient_ref_from(subject)
    created = []
    for _, data in files:
        text = pdf_bytes_to_text(data)
        packet = LabPacket(
            clinic_id=clinic.id,
            patient_ref_hash="",
            encrypted_patient_ref="",
            status="new" if text.strip() else "manual_review",
            created_by=member.user_id,
            source="email",
            encrypted_source_text=encrypt_field(text),
        )
        from app.api.routes.clinics import ref_hash  # shared patient-reference hashing

        db.add(packet)
        db.flush()
        # No code in the subject: give this lab its own code so it never shares history.
        own_ref = patient_ref or f"EMAIL-{packet.id[-8:].upper()}"
        packet.encrypted_patient_ref = encrypt_field(own_ref)
        packet.patient_ref_hash = ref_hash(clinic.id, own_ref)
        packet.file_key = f"intake/{clinic.id}/{packet.id}.pdf.enc"
        store_private_bytes(packet.file_key, encrypt_bytes(data))
        write_audit(
            db, member.user_id, "", "packet_received_by_email", "lab_packet", packet.id,
            {"clinic_id": clinic.id, "readable": bool(text.strip())},
        )
        created.append(packet.id)
    db.commit()
    return {"status": "accepted", "labs": len(created)}


@router.post("/email/{token}")
async def receive_email(token: str, request: Request, db: Session = Depends(get_db)):
    check_token(token)
    raw = await raw_message_from_request(request)
    if not raw:
        return {"status": "ignored", "reason": "no_message"}
    # Always answer 200 for a message we could read, so the provider doesn't retry it.
    return process_message(db, raw)

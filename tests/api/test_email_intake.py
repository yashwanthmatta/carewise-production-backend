import base64
import json
from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import decrypt_bytes
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import LabPacket
from app.services.storage import storage_root
from tests.api.test_reports_and_access_control import auth_headers

PDF = (Path(__file__).parent.parent / "fixtures" / "sample_lab.pdf").read_bytes()


@pytest.fixture(autouse=True)
def intake(monkeypatch):
    monkeypatch.setattr(settings, "inbound_email_domain", "in.example.com")
    monkeypatch.setattr(settings, "inbound_email_token", "intake-secret")


def clinic_with_owner(client):
    headers, email = auth_headers(client)
    clinic = client.post("/clinics", json={"name": "Maple", "clinician_name": "Dr. Lee"}, headers=headers).json()
    return headers, email, clinic


def raw_email(sender, to, subject="DEID JD-1042 lipids", attach=True):
    message = EmailMessage()
    message["From"] = f"Dr. Lee <{sender}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content("Forwarding this lab.")
    if attach:
        message.add_attachment(PDF, maintype="application", subtype="pdf", filename="lab.pdf")
    return message.as_bytes()


def test_forwarded_lab_lands_encrypted_in_clinic_inbox_and_drafts_on_screen():
    with TestClient(create_app()) as client:
        headers, email, clinic = clinic_with_owner(client)
        address = clinic["intake_address"]
        assert address.startswith("labs+") and address.endswith("@in.example.com")

        # SendGrid Inbound Parse with "send raw" posts the MIME message as the "email" field.
        posted = client.post("/inbound/email/intake-secret", data={"email": raw_email(email, address).decode()})
        assert posted.json() == {"status": "accepted", "labs": 1}

        inbox = client.get(f"/clinics/{clinic['id']}/packets", headers=headers).json()
        assert inbox[0]["status"] == "new" and inbox[0]["source"] == "email" and inbox[0]["patient_ref"] == "JD-1042"
        packet_id = inbox[0]["id"]
        source = client.get(f"/clinics/{clinic['id']}/packets/{packet_id}/source", headers=headers).json()["text"]
        assert "LDL Chol Calc" in source

        early = client.post(f"/clinics/{clinic['id']}/packets/{packet_id}/approve", json={"summary": "x"}, headers=headers)
        assert early.status_code == 409
        markers = [{"name": "LDL cholesterol", "value": "118", "unit": "mg/dL", "range": "0-99", "status": "Above the lab's range"}]
        drafted = client.put(
            f"/clinics/{clinic['id']}/packets/{packet_id}",
            json={"summary": "Your LDL is above the lab's range.", "questions": [], "markers": markers, "lab_date": "2026-10-01"},
            headers=headers,
        ).json()
        assert drafted["status"] == "draft" and drafted["markers"][0]["value"] == "118" and drafted["lab_date"] == "2026-10-01"
        approved = client.post(
            f"/clinics/{clinic['id']}/packets/{packet_id}/approve",
            json={"summary": "Your LDL is above the lab's range.", "questions": []},
            headers=headers,
        ).json()
        assert approved["edited"] is False
        trail = [step["action"] for step in client.get(f"/clinics/{clinic['id']}/packets/{packet_id}/audit", headers=headers).json()]
        assert trail[0] == "Received by email" and "Draft created" in trail

    with SessionLocal() as db:
        packet = db.scalars(select(LabPacket)).one()
        stored = (storage_root() / packet.file_key).read_bytes()
        assert stored[:4] != b"%PDF" and decrypt_bytes(stored) == PDF
        assert "LDL" not in packet.encrypted_source_text


def test_intake_refuses_strangers_missing_deid_bad_token_and_unknown_address():
    with TestClient(create_app()) as client:
        _, email, clinic = clinic_with_owner(client)
        address = clinic["intake_address"]
        assert client.post("/inbound/email/wrong", content=raw_email(email, address)).status_code == 404
        stranger = client.post("/inbound/email/intake-secret", content=raw_email("someone@else.com", address))
        assert stranger.json()["reason"] == "sender_not_in_clinic"
        no_deid = client.post("/inbound/email/intake-secret", content=raw_email(email, address, subject="Fwd: lab for John Smith"))
        assert no_deid.json()["reason"] == "missing_deid_confirmation"
        no_pdf = client.post("/inbound/email/intake-secret", content=raw_email(email, address, attach=False))
        assert no_pdf.json()["reason"] == "no_pdf"
        unknown = client.post("/inbound/email/intake-secret", content=raw_email(email, "labs+zzzzzzzzzzzz@in.example.com"))
        assert unknown.json()["reason"] == "unknown_address"
    with SessionLocal() as db:
        assert db.scalars(select(LabPacket)).all() == []


def test_amazon_ses_notification_format():
    with TestClient(create_app()) as client:
        headers, email, clinic = clinic_with_owner(client)
        notification = {
            "Type": "Notification",
            "Message": json.dumps({
                "receipt": {"action": {"type": "SNS", "encoding": "BASE64"}},
                "content": base64.b64encode(raw_email(email, clinic["intake_address"], subject="Fwd: DEID AB-700")).decode(),
            }),
        }
        assert client.post("/inbound/email/intake-secret", json=notification).json()["labs"] == 1
        assert client.get(f"/clinics/{clinic['id']}/packets", headers=headers).json()[0]["patient_ref"] == "AB-700"

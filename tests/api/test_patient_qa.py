import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import LabPacket, PatientQuestion
from tests.api.test_assistant import fake_client, text_response
from tests.api.test_docbridge import draft, make_clinic
from tests.api.test_reports_and_access_control import auth_headers

SUMMARY = "Hi,\n\nYour LDL cholesterol is above the usual target.\n\nWe'll go over it at your next visit."


def approved(client, headers, clinic_id, ref, value, lab_date):
    packet = draft(client, headers, clinic_id, value=value, lab_date=lab_date, ref=ref)
    response = client.post(
        f"/clinics/{clinic_id}/packets/{packet['id']}/approve",
        json={"summary": SUMMARY, "questions": ["What LDL goal fits me?"]},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def enable_qa(client, headers, clinic_id):
    response = client.put(
        f"/clinics/{clinic_id}/settings",
        json={"name": "Maple Family Practice", "tone": "friendly", "retention_days": 90, "patient_qa_enabled": True},
        headers=headers,
    )
    assert response.status_code == 200 and response.json()["patient_qa_enabled"] is True


def ask(client, token, question):
    return client.post("/clinics/packets/qa", json={"token": token, "question": question})


def test_answers_cite_only_this_patients_approved_data(monkeypatch):
    reply = json.dumps({
        "answer": "Your LDL went from 171 to 148 mg/dL. Both are above the lab's usual range.",
        "citations": ["lab:LDL cholesterol:2026-10-01", "lab:LDL cholesterol:2026-04-01", "lab:Other:2026-01-01"],
        "deflect_to_doctor": False,
    })
    messages = fake_client(monkeypatch, text_response(reply))
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        enable_qa(client, owner, clinic_id)
        approved(client, owner, clinic_id, "JD-1042", "171", "2026-04-01")
        current = approved(client, owner, clinic_id, "JD-1042", "148", "2026-10-01")
        # Another patient at the same clinic, an unapproved draft for this patient, and
        # the same reference at another clinic must never reach the model.
        approved(client, owner, clinic_id, "ZZ-9999", "333", "2026-09-01")
        draft(client, owner, clinic_id, value="222", lab_date="2026-11-01", ref="JD-1042")
        other_owner, other_clinic = make_clinic(client)
        approved(client, other_owner, other_clinic, "JD-1042", "444", "2026-08-01")

        response = ask(client, current["patient_token"], "Is this better than last time?")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["deflect_to_doctor"] is False
        assert body["citations"] == ["lab:LDL cholesterol:2026-10-01", "lab:LDL cholesterol:2026-04-01"]  # invented id dropped

        sent = messages.calls[0]["messages"][0]["content"]
        assert "148" in sent and "171" in sent and "summary:paragraph_2" in sent
        for leaked in ("333", "222", "444", "ZZ-9999"):
            assert leaked not in sent, leaked
        assert "ONLY the numbered" in messages.calls[0]["system"]

        # Logged encrypted for safety review; the owner can read it, others cannot.
        log = client.get(f"/clinics/{clinic_id}/patient-questions", headers=owner)
        assert log.status_code == 200 and log.json()[0]["question"] == "Is this better than last time?"
        stranger, _ = auth_headers(client)
        assert client.get(f"/clinics/{clinic_id}/patient-questions", headers=stranger).status_code in (403, 404)
    with SessionLocal() as db:
        row = db.scalars(select(PatientQuestion)).one()
        assert "better" not in row.encrypted_question and row.reason == "answered"


def test_diagnosis_treatment_and_emergencies_go_to_the_doctor_without_the_model(monkeypatch):
    messages = fake_client(monkeypatch, text_response("{}"))
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        enable_qa(client, owner, clinic_id)
        token = approved(client, owner, clinic_id, "JD-1", "148", "2026-10-01")["patient_token"]
        for question, reason in [("Do I have diabetes?", "doctor"), ("Should I take a statin?", "medicines"), ("I have chest pain", "911")]:
            body = ask(client, token, question).json()
            assert body["deflect_to_doctor"] is True and reason in body["answer"], question
        assert messages.calls == []


def test_unsafe_or_unsupported_model_answers_are_replaced(monkeypatch):
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        enable_qa(client, owner, clinic_id)
        token = approved(client, owner, clinic_id, "JD-1", "148", "2026-10-01")["patient_token"]
        for reply in [
            json.dumps({"answer": "Taking 20 mg daily would lower it.", "citations": ["summary:paragraph_2"], "deflect_to_doctor": False}),
            json.dumps({"answer": "LDL is the bad cholesterol.", "citations": [], "deflect_to_doctor": False}),
            "not json at all",
            json.dumps({"answer": "x", "citations": ["summary:paragraph_2"], "deflect_to_doctor": True}),
            # Found by the independent review: diagnoses, reassurance, medicine names, amounts.
            json.dumps({"answer": "An A1c of 7.2 means you have diabetes.", "citations": ["summary:paragraph_2"]}),
            json.dumps({"answer": "This result is nothing to worry about.", "citations": ["summary:paragraph_2"]}),
            json.dumps({"answer": "Your doctor may talk about atorvastatin.", "citations": ["summary:paragraph_2"]}),
            json.dumps({"answer": "Take 2 tablets of lisinopril daily.", "citations": ["summary:paragraph_2"]}),
        ]:
            fake_client(monkeypatch, text_response(reply))
            body = ask(client, token, "What does high LDL mean?").json()
            assert body["deflect_to_doctor"] is True and "20 mg" not in body["answer"], reply


def test_links_that_are_not_approved_or_expired_cannot_ask(monkeypatch):
    fake_client(monkeypatch, text_response("{}"))
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        enable_qa(client, owner, clinic_id)
        packet = approved(client, owner, clinic_id, "JD-1", "148", "2026-10-01")
        assert ask(client, "x" * 40, "What does high LDL mean?").status_code == 404
        with SessionLocal() as db:
            db.get(LabPacket, packet["id"]).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            db.commit()
        assert ask(client, packet["patient_token"], "What does high LDL mean?").status_code == 404


def test_without_a_key_only_the_fixed_replies_work(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        enable_qa(client, owner, clinic_id)
        token = approved(client, owner, clinic_id, "JD-1", "148", "2026-10-01")["patient_token"]
        assert ask(client, token, "What does high LDL mean?").status_code == 503
        assert ask(client, token, "Do I have diabetes?").json()["deflect_to_doctor"] is True
        assert client.get("/features").json()["patient_qa"] is False


def test_questions_are_deleted_with_their_lab(monkeypatch):
    from app.api.routes.maintenance import run_purge

    fake_client(monkeypatch, text_response("{}"))
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        enable_qa(client, owner, clinic_id)
        packet = approved(client, owner, clinic_id, "OLD-1", "148", "2026-10-01")
        ask(client, packet["patient_token"], "Do I have diabetes?")
    with SessionLocal() as db:
        db.get(LabPacket, packet["id"]).created_at = datetime.now(timezone.utc) - timedelta(days=120)
        db.commit()
        assert run_purge(db, datetime.now(timezone.utc))["patient_questions"] == 1
        assert db.scalars(select(PatientQuestion).where(PatientQuestion.packet_id == packet["id"])).all() == []


def test_questions_are_off_until_the_clinic_owner_turns_them_on(monkeypatch):
    messages = fake_client(monkeypatch, text_response("{}"))
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        packet = approved(client, owner, clinic_id, "JD-1", "148", "2026-10-01")
        assert client.post("/clinics/packets/view", json={"token": packet["patient_token"]}).json()["questions_enabled"] is False
        assert ask(client, packet["patient_token"], "What does high LDL mean?").status_code == 403
        assert messages.calls == []
        invite = client.post(f"/clinics/{clinic_id}/invites", json={"role": "clinician"}, headers=owner).json()
        colleague, _ = auth_headers(client)
        client.post("/clinics/join", json={"code": invite["code"], "display_name": "Dr. Kim"}, headers=colleague)
        body = {"name": "Maple Family Practice", "tone": "friendly", "retention_days": 90, "patient_qa_enabled": True}
        assert client.put(f"/clinics/{clinic_id}/settings", json=body, headers=colleague).status_code == 403
        enable_qa(client, owner, clinic_id)
        assert client.post("/clinics/packets/view", json={"token": packet["patient_token"]}).json()["questions_enabled"] is True


def test_identifiers_in_the_question_are_removed_before_the_model(monkeypatch):
    messages = fake_client(monkeypatch, text_response(json.dumps({"answer": "ok", "citations": []})))
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        enable_qa(client, owner, clinic_id)
        token = approved(client, owner, clinic_id, "JD-1", "148", "2026-10-01")["patient_token"]
        ask(client, token, "My DOB: 03/14/1950, call 512-555-0134. Hi Maria Lopez here, what is LDL?")
        sent = messages.calls[0]["messages"][0]["content"]
        for gone in ("1950", "512-555-0134", "Maria", "Lopez"):
            assert gone not in sent, gone

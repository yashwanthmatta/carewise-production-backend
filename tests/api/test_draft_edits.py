import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import DraftEdit, LabPacket
from app.services.deidentify import deidentify_text
from app.services.draft_edits import word_edit_distance
from tests.api.test_docbridge import draft, make_clinic
from tests.api.test_reports_and_access_control import auth_headers

QUESTIONS = ["What LDL goal fits me?"]


def test_word_edit_distance():
    assert word_edit_distance("a b c", "a b c") == 0
    assert word_edit_distance("a b c", "a x c") == 1
    assert word_edit_distance("a b c", "a b c d e") == 2
    assert word_edit_distance("", "one two") == 2


def test_every_save_and_approval_is_recorded_with_server_side_distance():
    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        packet = draft(client, headers, clinic_id)
        # A save with edits, then an approval; any distance the browser sends is ignored.
        saved = client.put(
            f"/clinics/{clinic_id}/packets/{packet['id']}",
            json={"summary": "Your LDL cholesterol is a little above the usual target.", "questions": QUESTIONS, "edit_distance": 0},
            headers=headers,
        )
        assert saved.status_code == 200
        approved = client.post(
            f"/clinics/{clinic_id}/packets/{packet['id']}/approve",
            json={"summary": "Your LDL cholesterol is a little above the usual target.", "questions": QUESTIONS + ["When do I recheck?"]},
            headers=headers,
        )
        assert approved.status_code == 200
        # A second lab approved exactly as drafted.
        other = draft(client, headers, clinic_id, ref="JD-2000")
        assert client.post(
            f"/clinics/{clinic_id}/packets/{other['id']}/approve",
            json={"summary": "Your LDL cholesterol is above the usual target.", "questions": QUESTIONS},
            headers=headers,
        ).status_code == 200

        metrics = client.get(f"/clinics/{clinic_id}/edit-metrics", headers=headers).json()
        week = metrics["weeks"][0]
        assert week["model_version"] == "docbridge-rules-v1"
        assert week["approvals"] == 2 and week["saves"] == 1
        assert week["approval_without_edit_rate"] == 0.5
        assert metrics["edits_recorded_total"] == 3 and metrics["pairs_collected_total"] == 2
        assert client.get(f"/clinics/{clinic_id}/metrics", headers=headers).json()["approved_without_edits"] == 1

    with SessionLocal() as db:
        rows = db.scalars(select(DraftEdit).where(DraftEdit.packet_id == packet["id"]).order_by(DraftEdit.created_at)).all()
        assert [r.event for r in rows] == ["save", "approve"]
        assert rows[0].edit_distance == 2  # "a little" added
        assert json.loads(rows[1].edited_sections) == {"summary": True, "questions": True}
        assert rows[1].zero_edit_approval == 0 and rows[1].edit_distance > rows[0].edit_distance
        assert "LDL" not in rows[1].encrypted_original_text  # stored encrypted
        zero = db.scalars(select(DraftEdit).where(DraftEdit.packet_id == other["id"])).one()
        assert zero.zero_edit_approval == 1 and zero.edit_distance == 0


def test_training_export_is_owner_only_and_deidentified():
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        packet = draft(client, owner, clinic_id, ref="JD-1042")
        client.post(
            f"/clinics/{clinic_id}/packets/{packet['id']}/approve",
            json={"summary": "Hi Maria Lopez,\nYour LDL is 148 mg/dL (usual <100). Call 512-555-0134 or maria@example.com.\nDr. Lee, Maple Family Practice", "questions": QUESTIONS},
            headers=owner,
        )
        invite = client.post(f"/clinics/{clinic_id}/invites", json={"role": "clinician"}, headers=owner).json()
        colleague, _ = auth_headers(client)
        assert client.post("/clinics/join", json={"code": invite["code"], "display_name": "Dr. Kim"}, headers=colleague).status_code == 200
        assert client.get(f"/clinics/{clinic_id}/training-pairs.jsonl", headers=colleague).status_code == 403
        stranger, _ = auth_headers(client)
        assert client.get(f"/clinics/{clinic_id}/training-pairs.jsonl", headers=stranger).status_code in (403, 404)
        assert client.get(f"/clinics/{clinic_id}/edit-metrics", headers=stranger).status_code in (403, 404)

        export = client.get(f"/clinics/{clinic_id}/training-pairs.jsonl", headers=owner)
        assert export.status_code == 200
        pair = json.loads(export.text.strip().splitlines()[0])
        text = json.dumps(pair)
        for secret in ("Maria", "Lopez", "512-555-0134", "maria@example.com", "Dr. Lee", "Maple Family Practice", "JD-1042", "2026-10-01"):
            assert secret not in text, secret
        assert "148 mg/dL" in pair["chosen"] and pair["prompt"]["markers"][0]["value"] == "148"
        assert pair["prompt"]["lab_year"] == "2026" and pair["rejected"].startswith("Your LDL cholesterol")
        assert "De-identified edit pairs downloaded" in client.get(f"/clinics/{clinic_id}/audit.csv", headers=owner).text


def test_edits_are_deleted_with_their_labs():
    from app.api.routes.maintenance import run_purge

    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        old = draft(client, headers, clinic_id, ref="OLD-1")
        client.post(f"/clinics/{clinic_id}/packets/{old['id']}/approve", json={"summary": "ok", "questions": []}, headers=headers)
    with SessionLocal() as db:
        db.get(LabPacket, old["id"]).created_at = datetime.now(timezone.utc) - timedelta(days=120)
        db.commit()
        counts = run_purge(db, datetime.now(timezone.utc))
        assert counts["draft_edits"] == 1
        assert db.scalars(select(DraftEdit).where(DraftEdit.packet_id == old["id"])).all() == []

    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        packet = draft(client, headers, clinic_id)
        client.put(f"/clinics/{clinic_id}/packets/{packet['id']}", json={"summary": "edited", "questions": []}, headers=headers)
        assert client.delete("/privacy/me", headers=headers).status_code == 200
    with SessionLocal() as db:
        assert db.scalars(select(DraftEdit).where(DraftEdit.clinic_id == clinic_id)).all() == []


def test_deidentify_keeps_lab_values_and_drops_identifiers():
    text = (
        "Patient: John Q Smith\nDOB: 03/14/1950\nMRN: A12345\nAddress: 42 Maple Leaf Drive, Austin TX 78701\n"
        "Collected 2026-10-01, reported October 3, 2026. Hello John,\n"
        "LDL 148 mg/dL (ref <100) H. Potassium 4.2 mmol/L 3.5-5.3. WBC 11.6 x10^9/L 4.0-11.0. Age 93 years old."
    )
    out = deidentify_text(text, ["JD-1042"])
    for gone in ("John", "Smith", "1950", "A12345", "Maple Leaf", "Austin", "78701", "10-01", "October 3", "93"):
        assert gone not in out, gone
    for kept in ("LDL 148 mg/dL (ref <100) H", "4.2 mmol/L 3.5-5.3", "11.6 x10^9/L 4.0-11.0", "Collected 2026", "90+ years"):
        assert kept in out, kept

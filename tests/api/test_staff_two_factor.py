"""Staged staff two-step sign-in (CAREWISE_STAFF_TWO_FACTOR_REQUIRED). Synthetic accounts only."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.services import totp
from tests.api.test_care_access import DOC_A, PASSWORD, patient_with_records, readable, staff_headers


@pytest.fixture(autouse=True)
def staff(monkeypatch):
    monkeypatch.setattr(settings, "staff_emails", f"{DOC_A}:clinician")
    monkeypatch.setattr(settings, "staff_access_mode", "grants")


def grant(client, patient_headers, patient_id):
    response = client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": DOC_A}, headers=patient_headers)
    assert response.status_code == 200, response.text


def test_off_by_default_nothing_changes():
    assert settings.staff_two_factor_required is False
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        doc = staff_headers(client, DOC_A, "clinician")
        grant(client, patient_headers, patient_id)
        me = client.get("/auth/me", headers=doc).json()
        assert me["role"] == "clinician" and me["staff_two_factor_needed"] is False
        assert readable(client, doc, patient_id) == [200, 200]


def test_required_staff_without_two_step_act_as_patients_until_they_turn_it_on(monkeypatch):
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        doc = staff_headers(client, DOC_A, "clinician")
        grant(client, patient_headers, patient_id)
        monkeypatch.setattr(settings, "staff_two_factor_required", True)

        me = client.get("/auth/me", headers=doc).json()
        assert me["role"] == "patient" and me["staff_two_factor_needed"] is True
        assert readable(client, doc, patient_id) == [403, 403]
        assert client.get("/clinical-review/queue", headers=doc).status_code == 403

        # Not locked out: the same session can turn two-step sign-in on.
        secret = client.post("/auth/two-factor/setup", headers=doc).json()["secret"]
        enabled = client.post("/auth/two-factor/enable", json={"code": totp.code_at(secret, totp.current_step())}, headers=doc)
        assert enabled.status_code == 200

        me = client.get("/auth/me", headers=doc).json()
        assert me["role"] == "clinician" and me["staff_two_factor_needed"] is False
        assert readable(client, doc, patient_id) == [200, 200]
        # And every new sign-in now asks for the code.
        login = client.post("/auth/login", json={"email": DOC_A, "password": PASSWORD}).json()
        assert login["two_factor_required"] is True and login["access_token"] == ""


def test_required_setting_does_not_affect_patients(monkeypatch):
    monkeypatch.setattr(settings, "staff_two_factor_required", True)
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        me = client.get("/auth/me", headers=patient_headers).json()
        assert me["role"] == "patient" and me["staff_two_factor_needed"] is False
        assert readable(client, patient_headers, patient_id) == [200, 200]

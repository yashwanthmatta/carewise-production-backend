"""Clinic self-pay prices and visit summary sections (owner-entered, never estimated)."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.test_docbridge import draft, make_clinic
from tests.api.test_reports_and_access_control import auth_headers

PRICES = [{"cpt": "80061", "name": "Lipid panel", "usd": 24.5}, {"cpt": "83036", "name": "Hemoglobin A1c", "usd": 18}]


def join(client, owner, clinic_id, role):
    code = client.post(f"/clinics/{clinic_id}/invites", json={"role": role}, headers=owner).json()["code"]
    headers, _ = auth_headers(client)
    assert client.post("/clinics/join", json={"code": code, "display_name": role}, headers=headers).status_code == 200
    return headers


def test_owner_sets_prices_and_sections_and_the_summary_carries_them():
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        empty = client.get(f"/clinics/{clinic_id}/visit-settings", headers=owner).json()
        assert empty == {"prices": [], "prices_updated_at": None, "hidden_blocks": [], "coverage_checklist": []}
        saved = client.put(
            f"/clinics/{clinic_id}/visit-settings",
            json={"prices": PRICES, "hidden_blocks": ["agenda"], "coverage_checklist": ["  Ask about the patient's deductible  ", ""]},
            headers=owner,
        )
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["prices"] == [{"cpt": "80061", "name": "Lipid panel", "usd": 24.5}, {"cpt": "83036", "name": "Hemoglobin A1c", "usd": 18.0}]
        assert body["prices_updated_at"] and body["hidden_blocks"] == ["agenda"]
        assert body["coverage_checklist"] == ["Ask about the patient's deductible"]
        draft(client, owner, clinic_id)
        summary = client.get(f"/clinics/{clinic_id}/patients/JD-1042/summary", headers=owner).json()
        assert summary["settings"]["prices"][0]["cpt"] == "80061" and summary["settings"]["hidden_blocks"] == ["agenda"]


def test_price_date_changes_only_when_prices_change():
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        first = client.put(f"/clinics/{clinic_id}/visit-settings", json={"prices": PRICES}, headers=owner).json()["prices_updated_at"]
        again = client.put(f"/clinics/{clinic_id}/visit-settings", json={"prices": PRICES, "hidden_blocks": ["coverage"]}, headers=owner).json()
        assert again["prices_updated_at"] == first and again["hidden_blocks"] == ["coverage"]


def test_only_the_owner_changes_settings_but_the_team_can_read_them():
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        client.put(f"/clinics/{clinic_id}/visit-settings", json={"prices": PRICES}, headers=owner)
        for role in ("clinician", "front_desk"):
            member = join(client, owner, clinic_id, role)
            assert client.get(f"/clinics/{clinic_id}/visit-settings", headers=member).json()["prices"][0]["usd"] == 24.5
            assert client.put(f"/clinics/{clinic_id}/visit-settings", json={"prices": []}, headers=member).status_code == 403


def test_bad_price_lists_are_refused():
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        bad = [
            {"prices": [{"cpt": "8006", "name": "Too short", "usd": 10}]},
            {"prices": [{"cpt": "80061", "name": "Lipid", "usd": 0}]},
            {"prices": [{"cpt": "80061", "name": "Lipid", "usd": 100001}]},
            {"prices": [{"cpt": "80061", "name": "A", "usd": 10}, {"cpt": "80061", "name": "B", "usd": 12}]},
            {"hidden_blocks": ["prices-everywhere"]},
            {"coverage_checklist": ["x" * 201]},
            {"prices": [{"cpt": f"8{i:04d}", "name": "n", "usd": 1} for i in range(61)]},
        ]
        for payload in bad:
            assert client.put(f"/clinics/{clinic_id}/visit-settings", json=payload, headers=owner).status_code == 422, payload
        assert client.put(f"/clinics/{clinic_id}/visit-settings", json={"prices": [{"cpt": "0001U", "name": "PLA test", "usd": 99.99}]}, headers=owner).status_code == 200


def test_activity_log_records_the_change_without_prices():
    with TestClient(create_app()) as client:
        owner, clinic_id = make_clinic(client)
        client.put(f"/clinics/{clinic_id}/visit-settings", json={"prices": PRICES}, headers=owner)
        csv_text = client.get(f"/clinics/{clinic_id}/audit.csv", headers=owner).text
        assert "Visit summary settings changed" in csv_text and "24.5" not in csv_text

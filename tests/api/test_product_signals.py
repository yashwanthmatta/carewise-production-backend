from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import EarlyAccessSignup, ProductFeedback, UsageCounter


def test_usage_events_are_daily_counts_only():
    with TestClient(create_app()) as client:
        for _ in range(3):
            assert client.post("/product/events", json={"name": "report_explained"}).status_code == 200
        assert client.post("/product/events", json={"name": "demo_started", "source": "mobile"}).status_code == 200
        assert client.post("/product/events", json={"name": "anything_else"}).status_code == 422

    with SessionLocal() as db:
        rows = db.scalars(select(UsageCounter)).all()
        counts = {(row.name, row.source): row.count for row in rows}
        assert counts == {("report_explained", "web"): 3, ("demo_started", "mobile"): 1}


def test_feedback_comment_is_encrypted():
    with TestClient(create_app()) as client:
        response = client.post("/product/feedback", json={"helpful": False, "comment": "Too many words on the result page"})
        assert response.status_code == 200
        assert client.post("/product/feedback", json={"helpful": True}).status_code == 200

    with SessionLocal() as db:
        rows = db.scalars(select(ProductFeedback)).all()
        assert sorted(row.helpful for row in rows) == ["no", "yes"]
        assert all("Too many words" not in row.encrypted_comment for row in rows)


def test_feedback_comment_can_follow_once():
    with TestClient(create_app()) as client:
        answer = client.post("/product/feedback", json={"helpful": True})
        feedback_id = answer.json()["id"]
        assert client.post(f"/product/feedback/{feedback_id}/comment", json={"comment": "Loved the doctor brief"}).status_code == 200
        assert client.post(f"/product/feedback/{feedback_id}/comment", json={"comment": "Overwrite"}).status_code == 404
        assert client.post("/product/feedback/fb_missing/comment", json={"comment": "x"}).status_code == 404

    with SessionLocal() as db:
        rows = db.scalars(select(ProductFeedback)).all()
        assert len(rows) == 1 and rows[0].helpful == "yes" and rows[0].encrypted_comment


def test_early_access_needs_consent_and_dedupes():
    with TestClient(create_app()) as client:
        no_consent = client.post("/product/early-access", json={"email": "a@example.com", "consent": False})
        assert no_consent.status_code == 422
        first = client.post("/product/early-access", json={"email": "A@Example.com", "role": "caregiver", "consent": True})
        again = client.post("/product/early-access", json={"email": "a@example.com", "role": "patient", "consent": True})
        assert first.status_code == 200 and again.status_code == 200
        assert client.post("/product/early-access", json={"email": "not-an-email", "consent": True}).status_code == 422

    with SessionLocal() as db:
        rows = db.scalars(select(EarlyAccessSignup)).all()
        assert len(rows) == 1
        assert rows[0].role == "patient"
        assert "example.com" not in rows[0].encrypted_email


def test_founder_summary_is_off_without_token_and_protected_with_one(monkeypatch):
    with TestClient(create_app()) as client:
        monkeypatch.setattr(settings, "founder_token", "")
        assert client.get("/product/summary").status_code == 404

        monkeypatch.setattr(settings, "founder_token", "founder-secret-value")
        client.post("/product/events", json={"name": "report_explained"})
        client.post("/product/feedback", json={"helpful": True, "comment": "Clear"})
        client.post("/product/early-access", json={"email": "c@example.com", "role": "caregiver", "note": "Mum's thyroid", "consent": True})

        assert client.get("/product/summary").status_code == 401
        assert client.get("/product/summary", headers={"X-Founder-Token": "wrong"}).status_code == 401
        summary = client.get("/product/summary", headers={"X-Founder-Token": "founder-secret-value"})
        assert summary.status_code == 200
        body = summary.json()
        assert body["usage_totals"] == {"report_explained": 1}
        assert body["helpful"] == {"yes": 1, "no": 0}
        assert body["comments"][0]["comment"] == "Clear"
        assert body["early_access"][0]["email"] == "c@example.com"
        assert body["early_access"][0]["note"] == "Mum's thyroid"


def test_event_rate_limit_is_generous_but_bounded():
    with TestClient(create_app()) as client:
        codes = [client.post("/product/events", json={"name": "sample_opened"}).status_code for _ in range(122)]
        assert codes[:120] == [200] * 120
        assert codes[-1] == 429

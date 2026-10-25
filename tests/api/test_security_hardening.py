"""Token handling, API security headers and the secret-strength advisory."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from tests.api.test_reports_and_access_control import auth_headers


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_api_responses_carry_security_headers():
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


def test_forged_and_broken_tokens_are_refused():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        assert client.get("/subscriptions/me", headers=headers).status_code == 200
        real = headers["Authorization"].split()[1]
        exp = datetime.now(timezone.utc) + timedelta(minutes=5)
        cases = {
            "wrong secret": jwt.encode({"sub": "x", "role": "admin", "exp": exp}, "not-the-server-secret-" * 2, algorithm="HS256"),
            "alg none": jwt.encode({"sub": "x", "role": "admin", "exp": exp}, key=None, algorithm="none"),
            "expired": jwt.encode({"sub": "x", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, settings.clean_jwt_secret, algorithm="HS256"),
            "no subject": jwt.encode({"role": "admin", "exp": exp}, settings.clean_jwt_secret, algorithm="HS256"),
            "tampered": real[:-4] + ("AAAA" if not real.endswith("AAAA") else "BBBB"),
            "garbage": "not-a-token",
        }
        for name, token in cases.items():
            response = client.get("/subscriptions/me", headers=bearer(token))
            assert response.status_code == 401, (name, response.status_code)


def test_ready_reports_a_short_signing_secret_without_failing(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "short-secret")
    with TestClient(create_app()) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        assert any("CAREWISE_JWT_SECRET" in item for item in response.json()["advisories"])
    monkeypatch.setattr(settings, "jwt_secret", "x" * 48)
    with TestClient(create_app()) as client:
        assert client.get("/ready").json()["advisories"] == []

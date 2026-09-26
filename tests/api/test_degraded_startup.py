from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def test_production_with_missing_secrets_stays_up_but_blocks_other_routes(monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "jwt_secret", "")

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

        ready = client.get("/ready")
        assert ready.status_code == 503
        issues = ready.json()["detail"]["issues"]
        assert any("CAREWISE_JWT_SECRET" in issue for issue in issues)

        blocked = client.post("/auth/login", json={"email": "a@example.com", "password": "x"})
        assert blocked.status_code == 503


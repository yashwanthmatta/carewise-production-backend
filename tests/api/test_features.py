from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def test_report_explanations_on_by_default():
    with TestClient(create_app()) as client:
        assert client.get("/features").json()["report_explanations"] is True


def test_report_explanations_can_be_paused(monkeypatch):
    monkeypatch.setattr(settings, "report_explanations_paused", True)
    with TestClient(create_app()) as client:
        assert client.get("/features").json()["report_explanations"] is False

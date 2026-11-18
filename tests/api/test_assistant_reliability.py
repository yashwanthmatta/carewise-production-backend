"""Help chat reliability (18 Nov 2026): every provider failure is named precisely in the log, shown to
people as one calm message, and never logs the question; /assistant/status checks the key and model
without health data; the medicine reference only ever uses entries checked against their sources.
All data here is synthetic and no real provider is called."""

import logging
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes import assistant
from app.core.config import settings
from app.main import create_app
from app.services import medicine_reference

QUESTION = "What is Dolo 650? My dad takes it."


def provider_error(cls, status_code):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("provider said no", response=httpx.Response(status_code, request=request), body=None)


def failing_client(monkeypatch, exc):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    def create(**_):
        raise exc

    monkeypatch.setattr(assistant, "get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))))


def ask(question=QUESTION):
    with TestClient(create_app()) as client:
        return client.post("/assistant/chat", json={"messages": [{"role": "user", "content": question}]})


@pytest.mark.parametrize(
    ("exc", "status_code", "logged"),
    [
        (provider_error(anthropic.AuthenticationError, 401), 503, "provider_auth_rejected"),
        (provider_error(anthropic.PermissionDeniedError, 403), 503, "provider_permission_denied"),
        (provider_error(anthropic.NotFoundError, 404), 503, "provider_model_not_found"),
        (provider_error(anthropic.InternalServerError, 500), 502, "provider_error_500"),
        (anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com")), 504, "provider_timeout"),
        (anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")), 503, "provider_unreachable"),
    ],
)
def test_each_provider_failure_is_named_in_the_log_and_calm_for_people(monkeypatch, caplog, exc, status_code, logged):
    failing_client(monkeypatch, exc)
    with caplog.at_level(logging.WARNING):
        response = ask()
    assert response.status_code == status_code
    assert response.json()["detail"] == "The health assistant is temporarily unavailable. Please try again shortly."
    assert f"assistant request failed: {logged}" in caplog.text
    # Nothing the person typed, and no key, reaches the log.
    assert "Dolo" not in caplog.text and "test-key" not in caplog.text


def test_rate_limit_still_says_busy(monkeypatch):
    failing_client(monkeypatch, provider_error(anthropic.RateLimitError, 429))
    response = ask()
    assert response.status_code == 429


def test_client_has_a_timeout_and_bounded_retries(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    client = assistant.get_client()
    assert client.max_retries == 2
    assert float(client.timeout) == assistant.REQUEST_TIMEOUT_SECONDS


def test_status_reports_not_configured_without_a_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with TestClient(create_app()) as client:
        assert client.get("/assistant/status").json()["state"] == "not_configured"


def status_client(monkeypatch, outcome):
    calls = []

    def retrieve(model):
        calls.append(model)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(id=model)

    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(assistant, "get_client", lambda: SimpleNamespace(models=SimpleNamespace(retrieve=retrieve)))
    assistant._STATUS_CACHE.clear()
    return calls


def test_status_names_a_rejected_key_and_is_cached(monkeypatch):
    calls = status_client(monkeypatch, provider_error(anthropic.AuthenticationError, 401))
    with TestClient(create_app()) as client:
        first = client.get("/assistant/status").json()
        second = client.get("/assistant/status").json()
    assert first["state"] == "provider_auth_rejected" and first["model"] == settings.assistant_model
    assert second == first and len(calls) == 1
    assert "test-key" not in str(first)
    assistant._STATUS_CACHE.clear()


def test_status_ok_when_key_and_model_are_accepted(monkeypatch):
    status_client(monkeypatch, None)
    with TestClient(create_app()) as client:
        assert client.get("/assistant/status").json()["state"] == "ok"
    assistant._STATUS_CACHE.clear()


# ----- Medicine reference -----

VERIFIED_FIXTURE = {
    "version": "test",
    "entries": [
        {
            "id": "made-up-brand",
            "kind": "brand",
            "name": "Testamol 500",
            "aliases": ["testamol"],
            "market": "Testland",
            "active_ingredients": [{"name": "examplamide", "strength": "500 mg"}],
            "summary": "A made-up medicine used only in tests.",
            "sources": [{"title": "Test source", "url": "https://example.org/testamol", "checked": "2026-11-18"}],
            "review_status": "source-verified",
            "clinical_review": "none",
        },
        {"id": "pending", "kind": "brand", "name": "Pendomol", "aliases": ["pendomol"], "review_status": "pending-source-check"},
    ],
}


def test_shipped_reference_loads_and_uses_nothing_unverified():
    medicine_reference.load_reference.cache_clear()
    data = medicine_reference.load_reference()
    assert data["entries"], "the reference lists the names to verify"
    for entry in data["entries"]:
        if entry["review_status"] != "source-verified":
            # A pending entry holds names only: no facts that could leak into an answer.
            assert not entry.get("summary") and not entry.get("active_ingredients")
    assert medicine_reference.context_for(QUESTION) == "" or all(
        e["review_status"] == "source-verified" for e in medicine_reference.find_mentions(QUESTION)
    )


def test_pending_entries_never_reach_the_model(monkeypatch):
    medicine_reference.load_reference.cache_clear()
    calls = []
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", model="m", content=[SimpleNamespace(type="text", text="Answer.")])

    monkeypatch.setattr(assistant, "get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))))
    monkeypatch.setattr(medicine_reference, "load_reference", lambda: VERIFIED_FIXTURE)
    response = ask("What is pendomol?")
    assert response.status_code == 200 and response.json()["sources"] == []
    assert "<medicine_reference>" not in calls[0]["system"]


def test_verified_entry_is_given_to_the_model_with_its_source(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", model="m", content=[SimpleNamespace(type="text", text="Testamol 500 is examplamide.")])

    monkeypatch.setattr(assistant, "get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))))
    monkeypatch.setattr(medicine_reference, "load_reference", lambda: VERIFIED_FIXTURE)
    response = ask("what is testamol500?")
    assert response.json()["sources"] == [{"title": "Test source", "url": "https://example.org/testamol"}]
    system = calls[0]["system"]
    assert "<medicine_reference>" in system and "examplamide 500 mg" in system and "Test source, read 2026-11-18" in system


def test_whole_word_matching_only(monkeypatch):
    monkeypatch.setattr(medicine_reference, "load_reference", lambda: VERIFIED_FIXTURE)
    assert medicine_reference.find_mentions("is TESTAMOL safe?")
    assert medicine_reference.find_mentions("testamol-500 tablets")
    assert not medicine_reference.find_mentions("testamolecule levels")


def test_an_entry_marked_verified_without_sources_is_refused(monkeypatch, tmp_path):
    bad = tmp_path / "ref.json"
    bad.write_text('{"entries": [{"id": "x", "name": "X", "review_status": "source-verified", "summary": "s", "active_ingredients": [{"name": "y"}], "sources": [{"title": "t", "url": "https://e.org"}]}]}')
    monkeypatch.setattr(medicine_reference, "DATA_FILE", bad)
    medicine_reference.load_reference.cache_clear()
    with pytest.raises(ValueError):
        medicine_reference.load_reference()
    medicine_reference.load_reference.cache_clear()

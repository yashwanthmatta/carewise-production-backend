"""The live smoke run fails when the help assistant is switched on but not answering (19 Nov 2026).

A rejected AI key went unnoticed for two days because the run recorded "answered: false" and still
passed. These tests use no network."""

import io
import json
import urllib.error

from scripts import smoke_test_deploy as smoke


def test_switched_off_helper_is_not_a_failure():
    assert smoke.assistant_problem({"enabled": False}) == ""


def test_answering_helper_is_not_a_failure():
    assert smoke.assistant_problem({"enabled": True, "status": 200, "answered": True}) == ""


def test_helper_that_cannot_answer_fails_with_the_reason():
    problem = smoke.assistant_problem({"enabled": True, "status": 503, "answered": False, "provider_state": "provider_auth_rejected"})
    assert "not answering" in problem and "503" in problem and "provider_auth_rejected" in problem
    assert "chatbot-error-remediation" in problem


def test_status_endpoint_is_read_and_a_missing_one_is_named(monkeypatch):
    def fake_urlopen(request, timeout=0):
        if request.full_url.endswith("/assistant/status"):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b""))
        raise AssertionError("unexpected call")

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)
    assert smoke.check_assistant_status("https://api.example.org") == {"state": "status_endpoint_http_404"}

    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda request, timeout=0: Response(json.dumps({"state": "ok"}).encode()))
    assert smoke.check_assistant_status("https://api.example.org")["state"] == "ok"

import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import totp

PASSWORD = "change-me-long-password"


def signup(client):
    email = f"two-{uuid4().hex}@example.com"
    response = client.post("/auth/signup", json={"email": email, "password": PASSWORD, "role": "patient"})
    return email, {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_totp_matches_rfc_6238_test_vector():
    # RFC 6238 appendix B, SHA-1, T = 59 seconds -> 94287082 (8 digits); last 6 digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.code_at(secret, 59 // 30) == "287082"


def test_turn_on_sign_in_with_code_and_recovery_then_turn_off():
    with TestClient(create_app()) as client:
        email, headers = signup(client)
        setup = client.post("/auth/two-factor/setup", headers=headers).json()
        assert setup["otpauth_url"].startswith("otpauth://totp/CareWise")
        secret = setup["secret"]
        assert client.post("/auth/two-factor/enable", json={"code": "000000"}, headers=headers).status_code == 400
        enable_code = totp.code_at(secret, totp.current_step())
        enabled = client.post("/auth/two-factor/enable", json={"code": enable_code}, headers=headers).json()
        assert enabled["enabled"] is True and len(enabled["recovery_codes"]) == 8
        assert client.get("/auth/me", headers=headers).json()["two_factor_enabled"] is True

        first = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
        assert first["two_factor_required"] is True and first["access_token"] == ""
        # The code used to turn it on can't be replayed.
        replay = client.post("/auth/login/two-factor", json={"challenge": first["challenge"], "code": enable_code})
        assert replay.status_code == 401
        assert client.post("/auth/login/two-factor", json={"challenge": "user_x.1.bad", "code": "123456"}).status_code == 401

        recovery = enabled["recovery_codes"][0]
        ok = client.post("/auth/login/two-factor", json={"challenge": first["challenge"], "code": recovery})
        assert ok.status_code == 200 and ok.json()["access_token"]
        second = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
        assert client.post("/auth/login/two-factor", json={"challenge": second["challenge"], "code": recovery}).status_code == 401

        next_code = totp.code_at(secret, totp.current_step() + 1)
        new_headers = {"Authorization": f"Bearer {ok.json()['access_token']}"}
        off = client.post("/auth/two-factor/disable", json={"code": next_code}, headers=new_headers)
        assert off.json()["enabled"] is False
        plain = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
        assert plain["two_factor_required"] is False and plain["access_token"]


def test_challenge_expires(monkeypatch):
    from app.api.routes import auth

    with TestClient(create_app()) as client:
        email, headers = signup(client)
        secret = client.post("/auth/two-factor/setup", headers=headers).json()["secret"]
        client.post("/auth/two-factor/enable", json={"code": totp.code_at(secret, totp.current_step())}, headers=headers)
        challenge = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["challenge"]
        later = time.time() + auth.CHALLENGE_SECONDS + 5
        monkeypatch.setattr(auth.time, "time", lambda: later)
        code = totp.code_at(secret, totp.current_step(later) )
        assert client.post("/auth/login/two-factor", json={"challenge": challenge, "code": code}).status_code == 401

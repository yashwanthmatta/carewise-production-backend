"""Continue with Google / Apple / Microsoft. Synthetic identities only; the provider's token
endpoint and signing keys are replaced by a local RSA key, so no real account is used."""

import hashlib
import secrets
import time
import urllib.parse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models.carewise import AuthFlowToken, CareAccessGrant, User, UserIdentity
from app.services import oidc
from tests.api.test_reports_and_access_control import auth_headers, create_profile

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PASSWORD = "change-me-long-password"
ISSUERS = {"google": "https://accounts.google.com", "apple": "https://appleid.apple.com"}
WORK_TENANT = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    for name, value in {
        "google_client_id": "google-client.apps.example",
        "google_client_secret": "google-secret",
        "microsoft_client_id": "ms-client-id",
        "microsoft_client_secret": "ms-secret~with=equals",
        "apple_client_id": "com.followthrough.signin",
        "apple_team_id": "TEAMID1234",
        "apple_key_id": "KEYID12345",
        "apple_private_key": "configured",
        "public_api_url": "https://api.example.test",
        "sign_in_web_return_url": "https://web.example.test",
        "staff_emails": "doc@clinic.example:clinician",
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(oidc, "apple_client_secret", lambda: "signed-apple-secret")
    monkeypatch.setattr(oidc, "signing_key", lambda provider, token: KEY.public_key())
    provider_state.clear()
    monkeypatch.setattr(oidc, "post_form", fake_token_endpoint)


provider_state: dict = {}


def fake_token_endpoint(url, data):
    # The real token endpoint returns an ID token for the code; here the test decides its claims.
    provider_state["last_exchange"] = data
    claims = provider_state["claims"]
    return {"id_token": jwt.encode(claims, provider_state.get("key", KEY), algorithm="RS256")}


def claims_for(provider, sub, email, nonce, **extra):
    now = int(time.time())
    base = {"sub": sub, "aud": oidc.client_id(provider), "iat": now, "exp": now + 600, "nonce": nonce}
    if provider == "microsoft":
        tenant = extra.pop("tid", oidc.MICROSOFT_CONSUMER_TENANT)
        base.update(iss=f"https://login.microsoftonline.com/{tenant}/v2.0", tid=tenant)
    else:
        base["iss"] = ISSUERS[provider]
        base["email_verified"] = True if provider == "google" else "true"
    if email:
        base["email"] = email
    base.update(extra)
    return base


def start(client, provider, headers=None, link=False):
    secret = secrets.token_urlsafe(32)
    binding = hashlib.sha256(secret.encode()).hexdigest()
    path = f"/auth/oidc/{provider}/{'link-start' if link else 'start'}"
    response = client.post(path, json={"platform": "web", "binding": binding}, headers=headers or {})
    assert response.status_code == 200, response.text
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(response.json()["authorization_url"]).query))
    return secret, query


def provider_returns(client, provider, query, claims, method="get", **params):
    provider_state["claims"] = claims
    values = {"state": query["state"], "code": "provider-code", **params}
    if method == "post":
        response = client.post(f"/auth/oidc/{provider}/callback", data=values, follow_redirects=False)
    else:
        response = client.get(f"/auth/oidc/{provider}/callback", params=values, follow_redirects=False)
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    fragment = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).fragment))
    return location, fragment


def sign_in(client, provider, sub, email, headers=None, link=False, method="get", **extra):
    secret, query = start(client, provider, headers, link)
    _, fragment = provider_returns(client, provider, query, claims_for(provider, sub, email, query["nonce"], **extra), method)
    assert "signin-code" in fragment, fragment
    return client.post("/auth/oidc/exchange", json={"code": fragment["signin-code"], "secret": secret})


def users_with(email):
    with SessionLocal() as db:
        return db.scalars(select(User).where(User.email == email)).all()


def test_nothing_offered_until_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_client_secret", "")
    with TestClient(create_app()) as client:
        assert "google" not in client.get("/auth/providers").json()["providers"]
        binding = "a" * 64
        assert client.post("/auth/oidc/google/start", json={"binding": binding}).status_code == 404


def test_authorization_request_is_minimal_and_uses_pkce_state_nonce():
    with TestClient(create_app()) as client:
        _, query = start(client, "google")
        assert query["scope"] == "openid email"
        assert query["code_challenge_method"] == "S256" and query["code_challenge"]
        assert query["state"] and query["nonce"]
        assert query["redirect_uri"] == "https://api.example.test/auth/oidc/google/callback"
        _, ms = start(client, "microsoft")
        assert ms["scope"] == "openid email"  # no Mail, Calendars or Graph scopes
        _, apple = start(client, "apple")
        assert apple["response_mode"] == "form_post" and apple["scope"] == "email"


def test_new_google_user_then_existing_google_user():
    with TestClient(create_app()) as client:
        first = sign_in(client, "google", "g-sub-1", "new.person@example.com")
        assert first.status_code == 200, first.text
        assert first.json()["created"] is True and first.json()["access_token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {first.json()['access_token']}"})
        assert me.status_code == 200
        user_id = me.json()["user_id"] if "user_id" in me.json() else me.json().get("id")
        second = sign_in(client, "google", "g-sub-1", "new.person@example.com")
        assert second.status_code == 200 and second.json()["created"] is False
        me2 = client.get("/auth/me", headers={"Authorization": f"Bearer {second.json()['access_token']}"})
        assert (me2.json().get("user_id") or me2.json().get("id")) == user_id
        assert len(users_with("new.person@example.com")) == 1
        assert provider_state["last_exchange"]["code_verifier"]


def test_provider_email_change_keeps_the_same_account():
    with TestClient(create_app()) as client:
        assert sign_in(client, "google", "g-sub-2", "old@example.com").status_code == 200
        again = sign_in(client, "google", "g-sub-2", "renamed@example.com")
        assert again.status_code == 200 and again.json()["created"] is False
        assert users_with("renamed@example.com") == []


def test_same_email_never_merges_into_existing_account():
    with TestClient(create_app()) as client:
        client.post("/auth/signup", json={"email": "owner@example.com", "password": PASSWORD})
        attempt = sign_in(client, "google", "g-attacker", "owner@example.com")
        assert attempt.status_code == 409
        assert attempt.json()["detail"]["code"] == "email_in_use"
        assert "Sign in to that account first" in attempt.json()["detail"]["message"]
        with SessionLocal() as db:
            assert db.scalars(select(UserIdentity)).all() == []
        assert len(users_with("owner@example.com")) == 1


def test_link_google_to_signed_in_account_then_sign_in_with_it():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        linked = sign_in(client, "google", "g-link-1", "personal@gmail.example", headers=headers, link=True)
        assert linked.status_code == 200 and linked.json()["linked"] == "google"
        assert linked.json()["access_token"] == ""
        me = client.get("/auth/me", headers=headers).json()
        via_google = sign_in(client, "google", "g-link-1", "personal@gmail.example")
        assert via_google.status_code == 200
        me2 = client.get("/auth/me", headers={"Authorization": f"Bearer {via_google.json()['access_token']}"}).json()
        assert me2 == me


def test_identity_already_on_another_account_cannot_be_linked():
    with TestClient(create_app()) as client:
        assert sign_in(client, "google", "g-taken", "first@example.com").status_code == 200
        headers, _ = auth_headers(client)
        attempt = sign_in(client, "google", "g-taken", "first@example.com", headers=headers, link=True)
        assert attempt.status_code == 409 and attempt.json()["detail"]["code"] == "identity_in_use"


def test_link_started_by_someone_else_cannot_finish_in_victims_browser():
    # The attacker starts a link for their own account and sends the provider URL to a victim.
    # The victim's browser does not hold the attacker's secret, so the code cannot be used.
    with TestClient(create_app()) as client:
        attacker_headers, _ = auth_headers(client)
        _attacker_secret, query = start(client, "google", attacker_headers, link=True)
        _, fragment = provider_returns(client, "google", query, claims_for("google", "victim-sub", "victim@example.com", query["nonce"]))
        victim_try = client.post("/auth/oidc/exchange", json={"code": fragment["signin-code"], "secret": secrets.token_urlsafe(32)})
        assert victim_try.status_code == 400
        with SessionLocal() as db:
            assert db.scalars(select(UserIdentity)).all() == []


def test_codes_and_states_work_once():
    with TestClient(create_app()) as client:
        secret, query = start(client, "google")
        claims = claims_for("google", "g-once", "once@example.com", query["nonce"])
        _, fragment = provider_returns(client, "google", query, claims)
        assert client.post("/auth/oidc/exchange", json={"code": fragment["signin-code"], "secret": secret}).status_code == 200
        reused = client.post("/auth/oidc/exchange", json={"code": fragment["signin-code"], "secret": secret})
        assert reused.status_code == 400
        _, replay = provider_returns(client, "google", query, claims)
        assert replay == {"signin-error": "expired"}


def test_expired_state_and_handoff(monkeypatch):
    with TestClient(create_app()) as client:
        _, query = start(client, "google")
        with SessionLocal() as db:
            for row in db.scalars(select(AuthFlowToken)).all():
                row.expires_at = row.expires_at.replace(year=2000)
            db.commit()
        _, fragment = provider_returns(client, "google", query, claims_for("google", "g-exp", "exp@example.com", query["nonce"]))
        assert fragment == {"signin-error": "expired"}


def test_unknown_or_forged_state():
    with TestClient(create_app()) as client:
        response = client.get("/auth/oidc/google/callback", params={"state": "forged", "code": "x"}, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"].endswith("#signin-error=expired")


def test_state_for_one_provider_cannot_be_used_on_another():
    with TestClient(create_app()) as client:
        _, query = start(client, "google")
        response = client.get("/auth/oidc/microsoft/callback", params={"state": query["state"], "code": "x"}, follow_redirects=False)
        assert response.headers["location"].endswith("#signin-error=expired")


def test_cancelled_at_provider_changes_nothing():
    with TestClient(create_app()) as client:
        _, query = start(client, "google")
        response = client.get("/auth/oidc/google/callback", params={"state": query["state"], "error": "access_denied"}, follow_redirects=False)
        assert response.headers["location"] == "https://web.example.test/#signin-error=cancelled"
        with SessionLocal() as db:
            assert db.scalars(select(UserIdentity)).all() == []


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "someone-elses-client"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"iss": "https://accounts.evil.example"},
        {"nonce": "different-nonce"},
        "wrong_key",
    ],
    ids=["wrong-audience", "expired", "wrong-issuer", "wrong-nonce", "wrong-signature"],
)
def test_bad_id_tokens_are_refused(change):
    with TestClient(create_app()) as client:
        _, query = start(client, "google")
        claims = claims_for("google", "g-bad", "bad@example.com", query["nonce"])
        if change == "wrong_key":
            provider_state["key"] = OTHER_KEY
        else:
            claims.update(change)
        _, fragment = provider_returns(client, "google", query, claims)
        assert fragment == {"signin-error": "invalid"}
        assert users_with("bad@example.com") == []


def test_microsoft_personal_account_creates_account_and_work_account_must_link():
    with TestClient(create_app()) as client:
        personal = sign_in(client, "microsoft", "ms-personal", "someone@outlook.example")
        assert personal.status_code == 200 and personal.json()["created"] is True
        work = sign_in(client, "microsoft", "ms-work", "someone@company.example", tid=WORK_TENANT)
        assert work.status_code == 403 and work.json()["detail"]["code"] == "needs_existing_account"
        headers, _ = auth_headers(client)
        linked = sign_in(client, "microsoft", "ms-work", "someone@company.example", headers=headers, link=True, tid=WORK_TENANT)
        assert linked.status_code == 200 and linked.json()["linked"] == "microsoft"


def test_microsoft_issuer_must_match_tenant():
    with TestClient(create_app()) as client:
        _, query = start(client, "microsoft")
        claims = claims_for("microsoft", "ms-x", "x@outlook.example", query["nonce"])
        claims["iss"] = f"https://login.microsoftonline.com/{WORK_TENANT}/v2.0"
        _, fragment = provider_returns(client, "microsoft", query, claims)
        assert fragment == {"signin-error": "invalid"}


def test_apple_form_post_with_private_relay_email_and_no_name():
    relay = "abc123@privaterelay.appleid.com"
    with TestClient(create_app()) as client:
        first = sign_in(client, "apple", "apple-sub-1", relay, method="post", is_private_email="true")
        assert first.status_code == 200 and first.json()["created"] is True
        assert provider_state["last_exchange"]["client_secret"] == "signed-apple-secret"
        assert "code_verifier" not in provider_state["last_exchange"]
        # Later Apple sign-ins may carry no email at all; the subject still finds the account.
        again = sign_in(client, "apple", "apple-sub-1", "", method="post")
        assert again.status_code == 200 and again.json()["created"] is False
        assert len(users_with(relay)) == 1


def test_two_step_sign_in_still_required():
    with TestClient(create_app()) as client:
        assert sign_in(client, "google", "g-2fa", "twofa@example.com").status_code == 200
        with SessionLocal() as db:
            db.scalar(select(User).where(User.email == "twofa@example.com")).totp_enabled = 1
            db.commit()
        result = sign_in(client, "google", "g-2fa", "twofa@example.com")
        assert result.status_code == 200
        assert result.json()["two_factor_required"] is True and result.json()["access_token"] == ""


def test_clinic_accounts_cannot_use_provider_sign_in():
    with TestClient(create_app()) as client:
        refused = sign_in(client, "google", "g-doc", "doc@clinic.example")
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "staff_account"


def test_redirect_carries_only_a_one_time_code():
    with TestClient(create_app()) as client:
        _, query = start(client, "google")
        location, fragment = provider_returns(client, "google", query, claims_for("google", "g-url", "url@example.com", query["nonce"]))
        parsed = urllib.parse.urlparse(location)
        assert parsed.query == "" and list(fragment) == ["signin-code"]
        assert "url@example.com" not in location and "eyJ" not in location


def test_password_accounts_unchanged_and_provider_only_accounts_have_no_password():
    with TestClient(create_app()) as client:
        client.post("/auth/signup", json={"email": "classic@example.com", "password": PASSWORD})
        assert client.post("/auth/login", json={"email": "classic@example.com", "password": PASSWORD}).status_code == 200
        assert sign_in(client, "google", "g-nopw", "nopw@example.com").status_code == 200
        assert client.post("/auth/login", json={"email": "nopw@example.com", "password": PASSWORD}).status_code == 401


def test_sign_in_methods_list_and_safe_removal():
    with TestClient(create_app()) as client:
        only = sign_in(client, "google", "g-only", "only@example.com").json()
        headers = {"Authorization": f"Bearer {only['access_token']}"}
        listing = client.get("/auth/identities", headers=headers).json()
        assert listing["has_password"] is False and [i["provider"] for i in listing["identities"]] == ["google"]
        identity_id = listing["identities"][0]["id"]
        last = client.post(f"/auth/identities/{identity_id}/remove", json={}, headers=headers)
        assert last.status_code == 409 and last.json()["detail"]["code"] == "last_method"

        pw_headers, _ = auth_headers(client)
        sign_in(client, "google", "g-pw", "pw@example.com", headers=pw_headers, link=True)
        pw_identity = client.get("/auth/identities", headers=pw_headers).json()["identities"][0]["id"]
        wrong = client.post(f"/auth/identities/{pw_identity}/remove", json={"password": "wrong-password-123"}, headers=pw_headers)
        assert wrong.status_code == 403
        # Someone else's identity id is simply not found.
        assert client.post(f"/auth/identities/{identity_id}/remove", json={}, headers=pw_headers).status_code == 404


def test_account_deletion_removes_identities_and_care_team_grants(monkeypatch):
    # Postgres enforces foreign keys; turn them on in SQLite for this test so a leftover
    # identity or care-team grant would make deletion fail here too.
    monkeypatch.setattr(settings, "staff_emails", "doc@clinic.example:clinician")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):  # pragma: no cover - new connections only
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    try:
        with TestClient(create_app()) as client:
            with engine.connect() as connection:
                connection.execute(text("PRAGMA foreign_keys=ON"))
            headers, _ = auth_headers(client)
            patient_id = create_profile(client, headers)
            doc = client.post("/auth/signup", json={"email": "doc@clinic.example", "password": PASSWORD, "role": "clinician"})
            with SessionLocal() as db:
                db.execute(text("PRAGMA foreign_keys=ON"))
                db.scalar(select(User).where(User.email == "doc@clinic.example")).email_verified = "true"
                db.commit()
            grant = client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": "doc@clinic.example"}, headers=headers)
            assert grant.status_code == 200, grant.text
            sign_in(client, "google", "g-del", "del@example.com", headers=headers, link=True)
            deleted = client.delete("/privacy/me", headers=headers)
            assert deleted.status_code == 200, deleted.text
            doc_headers = {"Authorization": f"Bearer {doc.json()['access_token']}"}
            assert client.delete("/privacy/me", headers=doc_headers).status_code == 200
            with SessionLocal() as db:
                assert db.scalars(select(UserIdentity)).all() == []
                assert db.scalars(select(CareAccessGrant)).all() == []
    finally:
        event.remove(engine, "connect", _fk)

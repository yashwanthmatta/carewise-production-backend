"""Sign in with Google, Apple or Microsoft (OpenID Connect, authorization-code flow).

Token signatures are checked with PyJWT against each provider's published keys; nothing
here implements cryptography. The endpoints below are the ones each provider's OpenID
discovery document lists; they are fixed so a changed discovery document cannot redirect
sign-in elsewhere. Only identity scopes are asked for: no contacts, mail, calendar or Graph.
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

import jwt

from app.core.config import settings

MICROSOFT_CONSUMER_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"  # personal Microsoft accounts


@dataclass(frozen=True)
class Provider:
    name: str
    authorize_url: str
    token_url: str
    jwks_url: str
    scope: str
    pkce: bool
    form_post: bool  # Apple returns to the callback with a POST when email is requested


PROVIDERS = {
    "google": Provider(
        "google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://www.googleapis.com/oauth2/v3/certs",
        "openid email",
        pkce=True,
        form_post=False,
    ),
    "microsoft": Provider(
        "microsoft",
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "https://login.microsoftonline.com/common/discovery/v2.0/keys",
        "openid email",
        pkce=True,
        form_post=False,
    ),
    "apple": Provider(
        "apple",
        "https://appleid.apple.com/auth/authorize",
        "https://appleid.apple.com/auth/token",
        "https://appleid.apple.com/auth/keys",
        "email",
        pkce=False,  # Apple does not document PKCE; state, nonce and the signed client secret protect it
        form_post=True,
    ),
}


class SignInError(Exception):
    """A provider sign-in that must not continue. `code` is a short, safe reason."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class VerifiedIdentity:
    provider: str
    subject: str
    email: str
    email_verified: bool
    personal_account: bool  # Microsoft: a personal (consumer) account, not work or school


def setting(name: str) -> str:
    return settings.clean_env_value(getattr(settings, name, "") or "")


def client_id(provider: str) -> str:
    return setting(f"{provider}_client_id")


def configured(provider: str) -> bool:
    if provider == "apple":
        return all(setting(n) for n in ("apple_client_id", "apple_team_id", "apple_key_id")) and bool(
            settings.apple_private_key
        )
    if provider in ("google", "microsoft"):
        return bool(client_id(provider) and raw_secret(f"{provider}_client_secret"))
    return False


def enabled_providers() -> list[str]:
    return [name for name in ("google", "apple", "microsoft") if configured(name)]


def callback_url(provider: str) -> str:
    return f"{setting('public_api_url').rstrip('/')}/auth/oidc/{provider}/callback"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def authorization_url(provider: str, state: str, nonce: str, code_challenge: str) -> str:
    spec = PROVIDERS[provider]
    params = {
        "client_id": client_id(provider),
        "redirect_uri": callback_url(provider),
        "response_type": "code",
        "scope": spec.scope,
        "state": state,
        "nonce": nonce,
    }
    if spec.pkce:
        params.update(code_challenge=code_challenge, code_challenge_method="S256")
    if spec.form_post:
        params["response_mode"] = "form_post"
    if provider == "google":
        params["prompt"] = "select_account"
    if provider == "microsoft":
        params["prompt"] = "select_account"
    return f"{spec.authorize_url}?{urllib.parse.urlencode(params)}"


def apple_client_secret() -> str:
    # Apple's client secret is a short-lived ES256 token signed with the team's private key.
    now = int(time.time())
    key = settings.apple_private_key.replace("\\n", "\n")
    return jwt.encode(
        {"iss": setting("apple_team_id"), "iat": now, "exp": now + 300, "aud": "https://appleid.apple.com", "sub": client_id("apple")},
        key,
        algorithm="ES256",
        headers={"kid": setting("apple_key_id")},
    )


def raw_secret(name: str) -> str:
    # Secrets are used as typed (only trimmed): the NAME=value clean-up would cut at "=".
    return (getattr(settings, name, "") or "").strip()


def client_secret(provider: str) -> str:
    return apple_client_secret() if provider == "apple" else raw_secret(f"{provider}_client_secret")


def post_form(url: str, data: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - fixed provider URL
        return json.loads(response.read().decode())


def exchange_code(provider: str, code: str, code_verifier: str) -> str:
    """Trade the authorization code for an ID token. Returns the raw ID token."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback_url(provider),
        "client_id": client_id(provider),
        "client_secret": client_secret(provider),
    }
    if PROVIDERS[provider].pkce:
        data["code_verifier"] = code_verifier
    try:
        body = post_form(PROVIDERS[provider].token_url, data)
    except Exception as exc:  # noqa: BLE001 - provider errors can quote request values
        raise SignInError("exchange_failed") from exc
    token = body.get("id_token") if isinstance(body, dict) else None
    if not token:
        raise SignInError("exchange_failed")
    return token


_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def signing_key(provider: str, token: str):
    client = _jwks_clients.get(provider)
    if client is None:
        client = _jwks_clients[provider] = jwt.PyJWKClient(PROVIDERS[provider].jwks_url, cache_keys=True)
    return client.get_signing_key_from_jwt(token).key


def truthy(value) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def verify_id_token(provider: str, token: str, nonce: str) -> VerifiedIdentity:
    try:
        key = signing_key(provider, token)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=client_id(provider),
            options={"require": ["exp", "iat", "iss", "aud", "sub"], "verify_iss": False},
            leeway=60,
        )
    except Exception as exc:  # noqa: BLE001 - every failure is the same refusal
        raise SignInError("invalid_token") from exc
    issuer = claims.get("iss", "")
    if provider == "google":
        issuer_ok = issuer in ("https://accounts.google.com", "accounts.google.com")
    elif provider == "apple":
        issuer_ok = issuer == "https://appleid.apple.com"
    else:
        tenant = str(claims.get("tid", ""))
        issuer_ok = bool(tenant) and issuer == f"https://login.microsoftonline.com/{tenant}/v2.0"
    if not issuer_ok:
        raise SignInError("invalid_token")
    if not nonce or not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SignInError("invalid_token")
    email = str(claims.get("email") or "").strip().lower()
    if provider == "microsoft":
        personal = claims.get("tid") == MICROSOFT_CONSUMER_TENANT
        # Microsoft confirms the address of personal accounts. Work or school directories
        # can set any address, so it is never treated as proof of owning that email.
        verified = personal and bool(email)
    else:
        personal = True
        verified = bool(email) and truthy(claims.get("email_verified"))
    return VerifiedIdentity(provider, str(claims["sub"]), email, verified, personal)

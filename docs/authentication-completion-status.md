# Authentication completion status

**Statuses:**
- **COMPLETE:** working in production and tested with real provider credentials.
- **IMPLEMENTED (tests pass):** the code is merged or in review, synthetic tests pass, and it is not switched on.
- **BLOCKED:** needs an owner action.
- **NOT STARTED**

Last updated: 2026-11-03.

## Audit of what existed (2026-11-03)

- Email and password sign-in: `/auth/signup`, `/auth/login`, PBKDF2 hashes, 12+ character passwords, rate limits per IP and per account.
- Two-step sign-in: TOTP with one-time recovery codes. It is optional for everyone, staff included.
- Sessions:
  - Access tokens are HS256 JWTs (stateless, `access_token_minutes`).
  - Refresh tokens are stored hashed and rotated on use; `/auth/logout` revokes them.
  - An access token stays valid until it expires, even after logout. There is no server-side session list.
- Email verification and password reset links: hashed, expiring tokens.
- Staff roles come only from `CAREWISE_STAFF_EMAILS`. Patient-record access needs a care-team grant (backend #55).
- Before this work there was no Google, Apple, Microsoft or phone sign-in, and no identity table.

## Status by method

| Item | Status | Evidence | What's left |
|---|---|---|---|
| Email and password | Working (unchanged) | Existing suites; a test confirms password accounts are unaffected | Passwordless email links: not started |
| Identity model (one account, many sign-in methods) | IMPLEMENTED (tests pass) | `user_identities` keyed by (provider, subject); migration 0025 up, down and up on SQLite | Postgres staging run |
| Google | IMPLEMENTED (tests pass), off | New user, returning user, provider email change, wrong audience, wrong issuer, wrong nonce, wrong signature, expired token, cancel, replay | **Owner:** create the OAuth client and set `CAREWISE_GOOGLE_CLIENT_ID` / `_SECRET` |
| Apple | IMPLEMENTED (tests pass), off | form_post callback, private relay email, later sign-ins with no email, ES256 client secret | **Owner:** Apple Developer account, Services ID, key. Then `CAREWISE_APPLE_*` |
| Microsoft | IMPLEMENTED (tests pass), off | Personal account creates an account; a work or school account must be linked; issuer must match the tenant | **Owner:** Entra app registration (personal + work accounts), `CAREWISE_MICROSOFT_*` |
| Phone one-time codes | NOT STARTED, by rule | — | Needs vendor and cost approval (Twilio Verify or similar) before any code is written to send messages |
| Account linking | IMPLEMENTED (tests pass) | Same email never merges; link only while signed in; a link URL sent to someone else cannot finish; an identity used by another account cannot be linked | Website screen (next) |
| Removing a sign-in method | IMPLEMENTED (tests pass) | The last method cannot be removed; the password is required when the account has one | Website screen |
| Staff accounts | Provider sign-in refused for clinicians and admins | Test | Enforce two-step sign-in for staff (staged); passkeys |
| Session security | Partial | Refresh rotation and revocation exist | Server-side session list, "sign out other devices", shorter access tokens |
| Website sign-in buttons | NOT STARTED | — | Buttons appear only for providers `/auth/providers` lists, with official branding |
| iPhone / Android | NOT STARTED | — | System-browser flow to the same API with return `carewise://auth`; no physical-device testing yet |
| Privacy policy update | NOT STARTED | — | Add Google, Apple and Microsoft as sign-in providers (identity only) before switching on |
| Production configuration | BLOCKED | — | Provider credentials (owner) |

## How provider sign-in works

1. The browser makes a random secret, keeps it, and sends its SHA-256 to `POST /auth/oidc/{provider}/start`. To connect a provider to a signed-in account it uses `/link-start` instead.
2. The API stores the state, nonce and PKCE verifier. They are single use, expire after 10 minutes and are stored hashed and encrypted. The API returns the provider URL. Scopes are `openid email` (Apple: `email`) only. No mail, calendar, contacts or Graph.
3. The provider returns to `/auth/oidc/{provider}/callback`. The API:
   - checks the state;
   - trades the code for an ID token, using the client secret on the server and PKCE;
   - verifies the ID token with PyJWT against the provider's published keys: signature, audience, issuer, expiry and nonce.
   It changes nothing yet. It redirects to the website or app with a one-time code in the URL fragment: no token, no email, no health data.
4. The browser posts the code and its secret to `/auth/oidc/exchange`. Only now is the user signed in, created or linked.

**Matching rules:**
- An account is found only by the provider's stable subject id.
- When an email already has an account, the answer is: "This email is already linked to an account. Sign in to that account first to connect this method."
- New accounts open only with a provider-confirmed email: Google with `email_verified`, Apple, or a personal Microsoft account.
- Two-step sign-in, when it is on, is still required after provider sign-in.

## Tests

`tests/api/test_oidc_sign_in.py` has 27 tests. The provider's keys and token endpoint are replaced with a local RSA key, and no real account is used.

Brief items covered: 1–12, 16–18, 21 (with foreign keys enforced), 22.

Not yet covered:
- 13–15 (phone, not built)
- 19–20 (session list, not built)
- 23 (entitlement: unchanged, because identities attach to the existing user id)
- 24–25 (covered by the existing care-access suites)

## Defect found and fixed during the audit

**Account deletion and care-team grants.** Account deletion did not remove care-team grants (backend #55). On Postgres, deleting a patient who had added a clinician, or deleting that clinician, would fail on a foreign key, and the account would not be deleted. Deletion now removes them, along with sign-in identities. A test with foreign keys enforced covers both.

## Owner actions

1. Decide which providers to switch on first. Google is the simplest.
2. Create the provider apps:
   - redirect URI `https://carewise-api.onrender.com/auth/oidc/{google|apple|microsoft}/callback`
   - set the `CAREWISE_*` variables in Render
3. Apple: a paid Apple Developer account is needed. **App Store rule:** an app that offers Google or Microsoft sign-in must also offer Sign in with Apple (or an equivalent private option). Check the current guideline before release.
4. Phone codes: approve a vendor and a budget first.

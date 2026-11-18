# Help chat: error remediation

Started 18 Nov 2026 from the owner's screenshot: "What is Dolo 650?" answered with "The full assistant isn't answering right now, so I can only use a short built-in list…".

## Root cause (verified in production logs)

| When (UTC) | What Render logged for `carewise-api` |
|---|---|
| 18 Nov 06:32:10 | `assistant request failed: AuthenticationError`, then `POST /assistant/chat` → 502 |
| 18 Nov 06:32:22 | the same, a second time |

- Anthropic rejects the API key the server sends. The key variable is set: an empty key returns 503 "not switched on", not 502. But Anthropic does not accept it, because it was revoked, belongs to another account, or was mistyped.
- The same error was first recorded as E-001 on 17 Nov in the frontend's `docs/application-error-remediation.md`. **It is not resolved.**
- It is not the model, the request format or the website:
  - `claude-opus-5-5` is a current model;
  - a wrong model returns NotFound, not an authentication error;
  - the request reaches the backend and fails at the provider.
- No code change can fix a rejected key. Only the owner can replace it.

## Owner: replace the key (about 5 minutes)

1. Sign in at console.anthropic.com, with the account that should pay for the helper.
2. Go to Settings → API keys and create a new key. Name it "FollowThrough production". Copy it once. Do not paste it into a chat, an email or a document.
3. In the Render dashboard, open the `carewise-api` service and go to Environment.
4. Edit `ANTHROPIC_API_KEY`, paste the new key, then click Save, rebuild and deploy.
5. When the deploy is live, open `https://carewise-api.onrender.com/assistant/status`. It should say `"state": "ok"`. This page is new in backend PR #60; until that PR is deployed, ask the chat a question instead.
6. Delete the old key in the Anthropic console.

If the status page says something other than `ok`:
- `provider_auth_rejected`: the key is still wrong.
- `provider_permission_denied`: the key works but the account cannot use the model.
- `provider_model_not_found`: the model setting is wrong.
- `provider_unreachable`: a network problem; try again later.

## Code changes (backend PR #60, frontend PR #172)

| Area | Before | After |
|---|---|---|
| Request timeout | none (the SDK default is 10 minutes) | 30 seconds, with 2 retries and backoff |
| Error names in the log | `AuthenticationError` and similar | `provider_auth_rejected`, `provider_permission_denied`, `provider_model_not_found`, `provider_timeout`, `provider_unreachable`, `provider_error_<status>`, `provider_rate_limited`. The question, answer and key are never logged |
| Status codes | 502 for everything | 503 when unavailable, 504 on timeout, 429 when busy, 502 on a provider error |
| Message to people | "The helper could not answer right now." | "The health assistant is temporarily unavailable. Please try again shortly." |
| Website offline text | "…I can only use a short built-in list, and it has nothing for…" | the same calm message, plus "If your question is about a medicine, your pharmacist can help today." |
| Health check | none | `GET /assistant/status`, which checks the key and model without health data. It is cached for 5 minutes |
| Model fallback | server-side fallback (existing) | unchanged; only Anthropic models, so no new data processor |
| Emergencies | built-in emergency answer before any network call (existing) | unchanged and still independent of the model |

## Still open

- **E-001:** the key (owner, above).
- **End-to-end test:** a real end-to-end test after the key is replaced. It has not been done, because the key is rejected.
- **Medicine reference:** see `medical-knowledge-system.md`. It is blocked on network access to the sources.

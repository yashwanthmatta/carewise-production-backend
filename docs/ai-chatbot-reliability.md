# Help chat reliability

## How a question flows (backend `app/api/routes/assistant.py`)

1. **Website, before any network call.** Emergency words get the fixed emergency answer. "Are you a doctor" and diagnosis questions get fixed answers.
2. **`POST /assistant/chat`.**
   - Rate limit: 30 an hour per caller.
   - The fixed system prompt, which includes the owner-approved medicine rule: it may say what a medicine is, never doses.
   - Optional report summary, only if the person ticks "share".
   - Entries from the source-checked medicine reference for any medicine named in the question.
3. **Anthropic Messages API.**
   - 30-second timeout and 2 retries with backoff.
   - Server-side model fallback within Anthropic.
4. **Output guard.** A reply that reads like dosing advice is withheld (`gives_dosing_advice`).
5. **Failures.** One calm message for people and a precise failure name in the log (see the remediation doc).

## Health check

`GET /assistant/status` returns `{state, model, checked_at}`:
- possible states are `ok`, `not_configured` and the failure names;
- it is cached for 5 minutes;
- it never includes the key or any health data.

A nightly synthetic check can call it. **Proposed, not yet scheduled:** the frontend's read-only check every 6 hours can add it. That routine is owned by this session.

## Privacy

- **Nothing stored:** nothing the person types is stored by FollowThrough. The conversation lives in the browser.
- **Logs:** logs carry only failure names and response time.
- **No other providers:** questions are sent only to Anthropic, the existing processor. No other provider is called. A fallback to another vendor would need the owner's approval and a privacy review.

## Not done (needs the key or owner decisions)

- **Latency:** median and p95 latency in production. `assistant request answered in N ms` is now logged, and can be read once answers succeed.
- **Streaming responses:** these would show the first words sooner. It is a frontend and backend change, planned after the key works.
- **Circuit breaker:** after repeated `provider_auth_rejected`, the website could stop calling for a few minutes. It is not needed while the status check is cached. Revisit after real traffic.

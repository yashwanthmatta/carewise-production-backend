# AI helper: quality dashboard

Only measured or verified values appear here. "Not measured" means exactly that.

Last updated: 2026-11-03.

## What the helper is today (audited from code)

| Item | Fact | Where |
|---|---|---|
| Endpoint | `POST /assistant/chat`. One request per question, not streamed. `max_tokens` 2000. | `app/api/routes/assistant.py` |
| Model | `claude-opus-5-5`, effort `low`, with the server-side fallback beta | `settings.assistant_model` |
| Turned on? | Only when `ANTHROPIC_API_KEY` is set. Otherwise the API returns 503 and the website uses its on-device answers. | `assistant_enabled()` |
| Knowledge | A fixed system prompt only: no retrieval, no knowledge base, no fine-tuning | same file |
| Report context | Only when the person ticks "share my result". The summary is wrapped in `<report_summary>` and treated as data | same file |
| Storage | Questions and answers are not stored by FollowThrough Health | same file; privacy policy |
| Rate limit | 30 questions per hour per IP | `check_rate_limit` |
| Languages | English and Spanish (an instruction to reply in Spanish). The Spanish has had no medical-language review. | `LANGUAGE_NOTE` |
| On-device answers | `help.js` answers common product questions without the API. The emergency message shows before any network call. | frontend |
| Tests | `tests/api/test_assistant.py`: off without a key, the safety prompt is sent, refusals, bad conversations, and product facts match the product. Frontend `help-answers.mjs`: every button named in an answer exists. | — |

## Fixed on 2026-11-03

- **Product facts drifted from the product.** The helper told people to use "Profile", which no longer exists (the screen is Account). It also said Family is "shared with caregivers", but that is not built and the website says "coming later".
  - The plan line is now built from the same plan list billing uses, so prices can't drift.
  - Deletion and download now point to Account → Your data.
  - The helper says that caregiver sharing is not available yet.
- **The plan list sold caregiver sharing too.** The billing plan list (`/subscriptions/plans`, shown on the website) said Family is "shared with caregivers". It now says "Sharing with siblings and caregivers: coming later", the same as the pricing card. Prices are unchanged.
- **Medical rules unchanged.** No diagnosis, no medicine names or doses, emergency first, no HIPAA or validation claims. A test checks the facts above.

## Not measured yet

Each of these needs paid API calls or production traffic data:
- answer accuracy
- hallucination rate
- latency (median and p95)
- cost per question
- error rate
- Spanish quality

**Owner decisions needed:**
1. A budget for a synthetic evaluation run, for example a fixed set of about 100 written questions run once against the current model.
2. Whether to log privacy-safe timing counts (durations only, never text) to measure latency in production.

Until then, no number is reported here.

## Not built (by design until approved)

- Retrieval or a medical knowledge base.
- Scheduled research jobs.
- Model switching or routing.
- Fine-tuning.

None of these should go live without clinical review. The current prompt keeps the helper to product guidance and general explanations.

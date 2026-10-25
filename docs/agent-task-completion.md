# Agent task completion: voice and audio agent

Updated 2026-10-25. Status words: COMPLETE, PARTIALLY COMPLETE, BLOCKED, NOT STARTED.

## Assigned task

Build and improve FollowThrough Health's voice and audio across the website, the iOS and Android
app, reminder calls and ads. Safe, on-device, never changing medical meaning. Add tests and
scheduled checks, write ad voiceovers, keep a status file.

## Requirements and status

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Audit voice and audio code in all three repositories | COMPLETE | Website: one Listen button. Mobile: no audio before this work. Backend: Twilio reminder calls. No microphone use anywhere. See `docs/voice-audio-agent-status.md` |
| 2 | Reminder call scripts clear for an older listener (English, Spanish draft) | COMPLETE (Spanish needs a human reviewer) | Backend #25 merged; Spanish wording fixes in the backend PR for this work |
| 3 | Fix the most important audio defect: lab values read wrong aloud | COMPLETE on the website, PARTIALLY COMPLETE on mobile | Frontend #109 merged with CI green. Mobile #48 open |
| 4 | Tests for decimals, units, ranges, negative numbers and negations, English and Spanish | COMPLETE | 36 exact cases and round-trip checks in frontend and mobile, run in CI |
| 5 | Mobile read-aloud (iOS and Android) | PARTIALLY COMPLETE | Mobile #48: code and tests done; needs review, merge, an EAS build and real-device testing |
| 6 | Ad voiceovers for the family campaigns (15 and 30 seconds, English, Spanish draft, subtitles, direction, music, mixing, disclosures) | PARTIALLY COMPLETE | 4 campaigns in `docs/voice-ads/` (Mom's Lab Report, What Does This Mean?, Three Simple Steps, DocBridge), checked by `tests/test_voice_ads.py`. Not recorded, approved or published. 4 more concepts from the brief not drafted |
| 7 | Scheduled audio quality checks | PARTIALLY COMPLETE | Audio QA workflow (nightly, frontend) is merged; first run started by hand on 2026-10-25. Live-site step waits until the wording is deployed |
| 8 | Status file | COMPLETE | `docs/voice-audio-agent-status.md` |
| 9 | Pause, resume, speed control, read one result | NOT STARTED | Backlog |
| 10 | Real-device listening tests | BLOCKED | Needs a person with an iPhone and an Android phone |
| 11 | A real Twilio test call | BLOCKED | Needs the founder's Twilio account and phone |
| 12 | Voice commands | NOT STARTED | Needs microphone; privacy and consent review first |

## Changed files

- Frontend (#109, merged): `script.js` (`spokenText`, Listen reads the range line),
  `scripts/eval/speech-cases.mjs`, `.github/workflows/frontend-ci.yml`,
  `.github/workflows/audio-qa.yml`, cache version 195 to 196 in the HTML pages and `sw.js`.
- Mobile (#48, open): `App.tsx` (Listen button), `src/spokenText.ts`, `src/productSignals.ts`
  (`listen_used`), `scripts/speech_cases_check.js`, `scripts/ci_check.js`, `package.json`,
  `package-lock.json` (`expo-speech ~58.0.3`), `docs/accessibility-device-checklist.md`.
- Backend (this PR): `app/services/reminder_calls.py` (Spanish fixes), `docs/voice-ads/*`,
  `scripts/build_voice_ads.py`, `tests/test_voice_ads.py`, this file,
  `docs/voice-audio-agent-status.md`.

## Tests performed (real runs)

- Frontend, locally: `node --check`, smoke test, run-eval (68 reports, 100% values), safety
  cases (34 passed), OCR correction, heading values, stress (seed 101), speech cases (36 cases
  and 8 reports passed). GitHub Frontend CI on #109: passed.
- Mobile, locally: `npm run ci:check` passed after merging the latest `main` (TypeScript, 27
  report cases, 36 read-aloud cases and 8 reports, product signals, offline EAS preflight).
- Backend, locally: `python -m pytest -q` (141 passed) and `ruff check .` (clean). The ad tests
  found real problems first (three versions ran over 15 or 30 seconds, one Spanish line too fast);
  the scripts were fixed, not the tests.

## Approvals needed

- Merge mobile #48 and this backend PR.
- Build and release the app (EAS) after #48.
- Approve the ad scripts, choose a voice actor or a licensed synthetic voice, and publish. Ad spend
  is the founder's decision.
- A qualified Spanish reviewer for calls, unit words and ads.

## PR links

- https://github.com/yashwanthmatta/carewise-production-backend/pull/25 (merged)
- https://github.com/yashwanthmatta/carewise-frontend/pull/109 (merged)
- https://github.com/yashwanthmatta/carewise-mobile-app/pull/48 (open)
- Backend PR for this work: see the PR that adds this file.

## Final status

**PARTIALLY COMPLETE.** The core fix is done and tested on the website. Mobile read-aloud and the ad
package are built and tested, but wait on review. Device listening, a real call and the
Spanish review need people.

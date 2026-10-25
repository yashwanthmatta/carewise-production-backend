# Agent task completion tracker

## Reminders agent

**Assigned task:** Make reminders reliable, private and easy to use on the website, iPhone and Android, with tests, monitoring and recurring automation. Details: `docs/reminders-agent-status.md`.

**Status: PARTIALLY COMPLETE** (2026-10-23)

### Requirements and state

| Requirement | State | Evidence |
|---|---|---|
| Audit reminder code in all three repos | Done | `docs/reminders-agent-status.md` "What exists today" |
| Five most important problems listed | Done | Same file, "Known problems" |
| Time zone and daylight-saving tests | Done, passing | `tests/api/test_reminders.py` (fall back, spring forward, Tokyo) |
| Lock-screen privacy | Fixed for the calendar file; calls and emails already generic | frontend PR #107, `scripts/reminder_calendar_test.mjs` |
| Honest status (tried vs delivered) | Fixed for the email; Twilio delivery result not read yet | backend PR #44 |
| Monitoring independent of Claude | Built: hourly health check | `.github/workflows/reminders-health.yml`, `GET /reminders/health` |
| Recurring agent runs | Set up: daily Claude scheduled task | status file, "Automation" |
| Phone test checklists | Written | status file, "Phone testing" |
| Status document | Done | `docs/reminders-agent-status.md` |
| Appointment, lab follow-up, visit-prep reminders | Not started: needs a new database table | Needs approval |
| iPhone and Android notifications | Not started: needs a notification library and store disclosures | Needs approval |
| Medication-specific features, caregiver sharing | Not started on purpose | Needs approval and a safety review |
| Snooze, completed history, one merged reminder list on the website | Not started | Next tasks |
| Tested on a physical phone | Not done | Needs a person with a phone |

### Changed files

- Backend (#44): `app/api/routes/reminders.py`, `tests/api/test_reminders.py`, `.github/workflows/reminders-health.yml`, `docs/reminders-agent-status.md`, `docs/agent-task-completion.md`
- Frontend (#107): `reminders.js`, `scripts/reminder_calendar_test.mjs`, `.github/workflows/frontend-ci.yml`, cache version 196 in HTML pages, `sw.js`, `scripts/build-info-pages.py`

### Tests run

- Backend `python -m pytest -q`: all pass. `ruff check .`: clean.
- Frontend `node scripts/reminder_calendar_test.mjs`, `node scripts/smoke_frontend.mjs`, cache-version check: pass.
- The health workflow's pass/fail step was checked with a healthy and an unhealthy sample reply.

### Pull requests

- https://github.com/yashwanthmatta/carewise-production-backend/pull/44
- https://github.com/yashwanthmatta/carewise-frontend/pull/107

### Blockers and approvals needed

- Approve a database table for appointment and follow-up reminders.
- Approve adding phone notifications to the mobile app (new permission; App Store and Play Store disclosures change).
- Merge #44 and #107. The hourly health check works only once #44 is deployed.
- Import the calendar file once into Apple Calendar and Google Calendar on a real phone.

## Round 3 independent code review (2026-10-23)

**Assigned task:** a third-round review of all three repositories. Verify earlier fixes, test the
extraction rules against adversarial inputs, review security, fix the highest-priority low-risk
issue with a regression test, open a focused PR, and document the findings.

**Final status: PARTIALLY COMPLETE**

| Requirement | Status | Notes |
|---|---|---|
| Pull and inspect all three repos | COMPLETE | Backend `07f9aa2`, frontend `8d6e756`, mobile `a1a0ce3` |
| Read earlier reviews and records | COMPLETE | Security assessment 2026-10-22, rules `.5` release record, PR #27 review comments |
| Recheck the 18 earlier findings | PARTIALLY COMPLETE | 4 are untested (photo corrections, source lines, doctor brief, accessibility). See `docs/code-review-round-3.md` |
| Adversarial extraction testing | COMPLETE for text input | 39 synthetic cases on web and mobile. PDFs: only the existing 68-PDF eval. Scanned and multi-column PDFs not tested beyond that |
| Security and authorization review | PARTIALLY COMPLETE | Existing isolation and role tests pass. No new penetration testing this round |
| Fix the top low-risk issue, with test | COMPLETE | R3-05: the pause switch now stops server explanations. Test fails before the fix and passes after |
| Fix extraction bugs R3-01 to R3-04 | BLOCKED | These are clinically consequential rule changes, so they need clinician approval. They are also in the frontend and mobile repos, which this reviewer can't push to |
| Mobile builds and device tests | NOT STARTED | No EAS credentials and no physical devices here |
| Automation | Not changed | Existing workflows: backend CI, nightly smoke, scheduled jobs, release candidate, Q&A safety check (manual) |
| Documentation | COMPLETE | `docs/code-review-round-3.md`, this file |

**Changed files:** `app/api/routes/reports.py`, `tests/api/test_explanations_pause.py`,
`docs/code-review-round-3.md`, `docs/agent-task-completion.md`.

**Tests:** backend `pytest`: 121 passed. `ruff check .`: clean. Frontend evals: 16/16, 34/34, and
200/200 at 100%.

**PR:** https://github.com/yashwanthmatta/carewise-production-backend/pull/46

**Approvals needed:** the clinical reviewer for R3-01 to R3-04, the owner for the frontend and
mobile changes, and the security/legal items from the 2026-10-22 assessment.

## Reviewer agent (independent re-check)

**Assigned task:** Re-check earlier review findings and fixes across the backend, website and app.
Reproduce defects with synthetic data, fix the verified ones, add tests, open PRs and keep a
re-check register. Register: `docs/code-review-recheck.md`.

**Status: PARTIALLY COMPLETE** (2026-10-23)

### Requirements and state

| Requirement | State | Evidence |
|---|---|---|
| Read earlier reviews, security assessment, release records | Done | Register, "Register" table (R-, S- rows) |
| Re-check earlier fixes (patient codes, Q&A, headings, vitamin D) | Done | R-01 to R-05 verified; R-02 contained (locked) |
| Adversarial synthetic reports | Done | 34 reports on both engines; findings N-01 to N-07 |
| Fix verified defects with tests | Done for N-01 to N-04, round 3 R3-01 and R3-03, R-06 (vitamin D3) and L-01 (email address in logs) | website PR #114, app PR #46, backend #46; new CI check `repeat-and-misread-values.mjs` (19 cases); app report cases 40 |
| No change to existing results | Verified | 0 of 160 review cases and 68 accuracy reports change; 10,000 random reports pass |
| Website and app parity | Verified | Identical output on 197 reports |
| DocBridge authorization | Verified | 15 tests plus a direct front-desk probe |
| Production check | Partly | Render API: live deploys match `main`; database still `0.0.0.0/0`; API on free plan. Direct HTTP blocked by the sandbox network policy |
| Mobile readiness | Source checks only | typecheck, ci:check, 35 report cases; no device evidence |
| N-05 to N-07, R3-04, R3-06 | Not fixed | Need a clinical, product or owner decision (register) |
| Round 3 PR #46 (pause switch R3-05) | Re-verified | `tests/api/test_explanations_pause.py` passes after merging `main` into the branch |

### Changed files

- Website #114: `script.js`, `scripts/eval/repeat-and-misread-values.mjs`, `.github/workflows/frontend-ci.yml`,
  `docs/releases/rules-2026-10-20.6.md`, `docs/clinical-rules-for-review.md`, `docs/PROJECT-STATUS.md`, cache version files
- App #46: `src/labPanel.ts`, `src/reportAnalysis.ts`, `scripts/report_cases_check.js`
- Backend (added to round-3 PR #46, which already holds the pause-switch fix): `docs/code-review-recheck.md`, `docs/agent-task-completion.md`

### Blockers and approvals needed

1. **Owner approval to merge website #114 and app #46** (rules .6). Merging the website deploys it to production.
   Clinician review of .2 to .6 is still needed before any version counts as validated.
2. Owner: remove `0.0.0.0/0` from `carewise-postgres` networking (S-02).
3. Owner: decide whether to pay for a non-free API plan (P-03).
4. Clinician: decisions on N-05 (two date columns), N-06 (negation after the symptom) and R3-04 (lab flag with no value).
5. A person with a phone: device, VoiceOver and TalkBack tests.

## Code review agent (2026-10-25)

**Assigned task:** independent review of all three repositories; fix the highest-priority safe
issue with a regression test and open a PR; keep a findings register.

**Final status: PARTIALLY COMPLETE**

| Requirement | Status | Evidence |
|---|---|---|
| Fix a verified issue with a test, and open a PR | COMPLETE | CR-008 in `docs/code-review-agent.md`. New test fails before the fix and passes after; backend 142 passed, `ruff` clean |
| Findings register | COMPLETE | `docs/code-review-agent.md` (only findings not already in `docs/code-review-recheck.md`) |
| Review the open PRs in the website and app repos | PARTIALLY COMPLETE | See the review comments on each PR; anything not reviewed is listed in the PR body |
| Production HTTP checks | BLOCKED | This container's network refuses followthroughhealth.com and the API |
| Native iOS/Android builds and devices | BLOCKED | Needs the owner's Apple and Google accounts and a physical phone |

**Changed files:** `app/services/deidentify.py`, `tests/api/test_draft_edits.py`,
`docs/code-review-agent.md`, `docs/agent-task-completion.md`.

**Approvals needed:** CR-004 needs the inbound email provider named. Owner items S-02 (database
network) and P-03 (free plan) are in `docs/code-review-recheck.md`.

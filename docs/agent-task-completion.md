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

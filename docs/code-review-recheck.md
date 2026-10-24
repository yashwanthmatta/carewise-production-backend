# Code review re-check register

Independent reviewer's register. Each row says what was checked and how. "Verified fixed" is used
only where a reproduction now passes. Statuses: **verified fixed** · **fixed in PR (not merged)** ·
**open** · **contained** (still present but switched off) · **untested**.

Last re-check: 2026-10-23. Repositories at: backend `c2d573a`, website `8717e12`, app `a1a0ce3` (all `main`).
Earlier rounds: PR #27 review comments, `docs/security-assessment-2026-10-22.md`, `docs/code-review-round-3.md`.

## How it was checked

- **Source code:** backend `pytest` (124 passed) and `ruff` (clean). Website CI suite run locally:
  accuracy, safety, photo correction, headings, 10,000 random reports. App `typecheck`,
  `ci:check` and `report:check`. 34 new adversarial synthetic reports were run through the
  website engine in a browser and through the app engine in Node.
- **Production:** Render API (read-only): services, deploys, database settings, request logs.
  Direct HTTP checks of followthroughhealth.com and carewise-api.onrender.com were **not possible**
  from the review sandbox, because its network policy blocks those hosts (proxy 403). So this register
  has no live HTTP, TLS or redirect evidence of its own. The website's `production-monitor.yml`
  is the source for those.
- All data was synthetic. No production data was read or changed.

## Register

| ID | Finding | Previous status | Current status | Severity | Evidence | Next action (owner / approval) |
|---|---|---|---|---|---|---|
| R-01 | Emailed-lab patient codes taken from subjects like "DEID LDL-100", "DEID Oct-2026" (two patients merged) | Blocking on PR #27 | **verified fixed** | High | `patient_ref_from` accepts only `REF-` codes (f5987cb). `DEID LDL-100`, `GLU-126`, `Oct-2026` → none; `DEID REF-1042`, `Re: DEID: REF-1042` → `REF-1042` | None |
| R-02 | Patient Q&A: unsafe answers passed the word filter, so safety relied on one unverified model check | Blocking on PR #27 | **contained** | High while switched on | Locked on the server unless `CAREWISE_PATIENT_QA_SAFETY_VERIFIED` is set (default false; 2d2d9c8). `test_patient_questions_stay_locked_until_the_safety_check` checks the 403. The filter still passes, for example, "within the target zone, so you can relax", "Your result is excellent", "Swapping soda for water may help" | Owner: keep the flag off. Before switching it on, run the real-model check on the PR #27 sentence list |
| R-03 | Safety verdict parser accepted text around `{"safe": true}` | Optional on PR #27 | **verified fixed** | Low | `unsafe, but {"safe": true}`, extra keys, duplicate keys and fenced JSON → False | None |
| R-04 | A test name in a heading took another test's value ("Lipid panel and A1C" read as A1C 228 %) | Fixed in rules .4 | **verified fixed** | High | `heading-values.mjs` passes. New cases ("Hemoglobin 13.5" then "A1c 5.4"; "Triglycerides" heading with no value) read correctly | None |
| R-05 | "Vitamin D, 25-hydroxy" with no result read as 25 | Fixed in rules .5 | **verified fixed** | High | "25-OH Vitamin D 18", "Vitamin D (25-hydroxy) 18", "Vitamin D, 25-hydroxy, total" then "32" read 18, 18 and 32 | None |
| R-06 | "Vitamin D3 25 ng/mL" read as 3 | Found by an earlier reviewer session; pushed without a PR | **fixed in PR (not merged)** | High | website #114, app #46; 6 heading cases | Owner approval and clinician review of rules .6 |
| N-01 | **A repeated test lost its second value.** "Potassium 4.1" then "Potassium 6.9" was explained as routine, "all within the lab's ranges" | New | **fixed in PR (not merged)** | **Critical** (missed danger-level value) | Reproduced on live rules .5 code. Fixed: urgent, with a "More than one result" finding. `scripts/eval/repeat-and-misread-values.mjs` | Owner approval and clinician review (new wording) |
| N-02 | "Previous LDL 98" then "Current LDL 151" explained as LDL 98, "In a better range" | New | **fixed in PR (not merged)** | High (false reassurance) | Now uses 151 and names 98 | Same as N-01 |
| N-03 | An OCR misread glued to letters was read as a result: "A1c S.9 %" → A1C 9 %; "Glucose 1O8" → 1 mg/dL, urgent | New | **fixed in PR (not merged)** | High | Neither is read now; dot leaders still are | Same as N-01 |
| R3-01 | A blank result took the low end of its range ("Potassium  mmol/L  3.5-5.1" → 3.5 "within"; also LDL → **0** "In a better range", A1C → 4) | Open (round 3) | **fixed in PR (not merged)** | High | Reproduced on .5 for the panel, LDL and A1C readers; fixed in website #114 and app #46; 4 eval cases | Owner approval and clinician review. Showing "not read, check the original" is new wording, still open |
| R3-02 | "Vitamin D3 32" read as 3 | Open (round 3) | **fixed in PR (not merged)** | High | Same as R-06 | Same as R-06 |
| R3-03 | A date in brackets read as the range ("2025-03"), so a high potassium was called "far below" | Open (round 3) | **fixed in PR (not merged)** | Medium | Unambiguous dates skipped. A first, too-broad date pattern changed 120 review cases; the comparison caught it and it was narrowed to 0 changes | Same as N-01 |
| R3-04 | A lab flag with no value (`Potassium HH`) disappears behind "within range" | Open (round 3) | **open** | High | Reproduced on .5 and .6 | Changes urgency, so it needs the clinician first |
| R3-05 | The pause switch did not stop server-side explanations | Fixed in backend PR #46 | **verified fixed (in PR, not merged)** | Medium | `test_explanations_pause.py` passes on the PR branch after merging `main` | Owner: merge backend #46 |
| R3-06 | Website runs explanations when `/features` can't be reached (pause can't take effect; app fails closed) | Open (round 3) | **open** | Medium | Code read only | Product decision: failing closed blocks first-time visitors while the free-plan API is asleep (P-03) |
| N-04 | `LDL cholesterol <100 mg/dL` with no result read as an LDL of 100, "In a better range" | New | **fixed in PR (not merged)** | Medium | The LDL, cholesterol, triglyceride and A1C reader skips a number right after `<`/`>`; `LDL 151 mg/dL <100 H` still reads 151; `Glucose <40` still urgent. 0 review cases change | Same as N-01 |
| N-05 | Two date columns on one line (`LDL cholesterol 98 151 mg/dL`) read the first, older value | New | **open** | High (false reassurance) | Reproduced on .5 and .6 | Design: detect several numbers before the unit, then ask the person to confirm |
| N-06 | `Chest pain: none`, `Fainting: no` (negation after the symptom) treated as a current emergency | New | **open** | Low (cautious direction) | Reproduced | Changes urgency behaviour, so it needs clinician approval first |
| N-07 | A result with no unit gets an assumed unit and isn't flagged | New | **open** | Low | `LDL cholesterol 151 <100` shown as mg/dL | Product decision |
| S-01 | DocBridge: other clinics, front desk, anonymous visitors, expired, revoked and replaced links | Closed with tests | **verified fixed** | High | 15 tests in `test_docbridge.py`. Extra direct probe: front desk gets 403 on `new-link`, `revoke-link`, `approve`, `settings`, `audit.csv`, `training-pairs.jsonl`, `patient-questions`. It can read clinic packets and mark follow-up, as designed | None |
| L-01 | A failed missed-reminder email logged the family member's email address (smtplib quotes refused addresses; `log.exception` wrote the full text) | New (2026-10-24 log audit) | **fixed in PR (not merged)** | Low (personal data in logs, tied to a medicine reminder) | `test_failed_missed_email_does_not_log_the_family_email_address` fails on `main` (address found in the log) and passes with the fix. The reminder call failure handler now logs only the error type too. No other `log.exception` calls remain. All 7 log calls in `app/` were read: none logs report text, values or summaries | Owner: merge backend #46 |
| S-02 | Production database reachable from any address (`ipAllowList 0.0.0.0/0`) | Open (H2) | **open** | High | Render API, 2026-10-23: `carewise-postgres` ipAllowList `0.0.0.0/0` | Owner: remove it in the Render dashboard (steps in `docs/security-assessment-2026-10-22.md`) |
| S-03 | Plain-text health columns (M1), single key (M2), no BAAs (M3), broad staff roles (M4), AI retention terms (V1) | Open | **open** (unchanged) | Medium / High (V1) | `docs/security-assessment-2026-10-22.md` | Owner and security-reviewer decisions; no migration without approval |
| P-01 | Production runs the latest `main` | Not recorded | **verified** (Render API) | n/a | API live deploy `c2d573a` = backend `main`; website live deploy `8717e12` = website `main`. Both `status: live` | None |
| P-02 | Live HTTP, TLS, redirects, rules version, `/ready` database check | Monitored by a workflow | **untested here** | n/a | Sandbox network policy blocks the hosts. Render request logs return no entries, so they give no evidence either way | Read `production-monitor.yml` run results; external uptime monitor (owner) |
| P-03 | Production API runs on Render's **free** web-service plan (`plan: free`, 1 instance) | Not recorded | **open** | Medium (reliability) | Render API. Free services sleep when idle (slow first request) and have no SLA | Owner decision (costs money) |
| M-01 | App build checks | n/a | **verified (source only)** | n/a | `tsc` clean, `ci:check` passes, 35 report cases pass, website and app outputs identical on 197 reports | Device, VoiceOver and TalkBack tests need a person with a phone; store accounts (owner) |

## Clinical rules version

Live: `2026-10-20.5` (not clinically validated). Proposed: `2026-10-20.6` (website #114 and app #46,
not validated). Frozen review candidate: `2026-10-20.2`, unchanged. Merging #114 deploys straight to
production, so it needs the owner's approval first.

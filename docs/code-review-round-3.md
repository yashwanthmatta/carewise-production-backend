# Code review, round 3

Date: 2026-10-23. Independent reviewer (Claude Code). Code reviewed: backend `main` at `07f9aa2`, frontend
`main` at `8d6e756`, mobile `main` at `a1a0ce3`. All test inputs were synthetic; no real patient data
and no production systems were touched.

This is a code review, not clinical validation. Nothing here means the medical explanations are
safe. Extraction and urgency findings need the clinician reviewer's sign-off before any rule changes.

## Confirmed bugs

### R3-01: A blank result takes its value from the reference range (High, safety)

- **Repos:** frontend `script.js:436` `readLabPanel`; mobile `src/labPanel.ts:261` `readLabPanel`.
  Both give the same output.
- **Reproduce:** `analyzeReportTextLocally("Test  Result  Units  Range\nPotassium        mmol/L  3.5-5.1\nSodium  140  mmol/L  135-145")`.
  Also try `"Potassium mmol/L 3.5-5.1"`.
- **Actual:** potassium is read as `value: 3.5`, `status: "within"`. The headline says "Your lab
  results are within the lab's ranges. All 2 results are inside the ranges."
- **Expected:** a result with no value is never given a number. It is shown as "not read, check the
  original", and the "all within range" headline is not shown.
- **Impact:** a missing potassium (for example a hemolysed sample) is presented to the patient as a
  normal result. This breaks the "never silently inherit another value" rule.
- **Proposed fix:** if the only number after the test name is the start of a range (`3.5-5.1`, `<`,
  `>`), treat the value as missing. Make the same change on web and mobile, release it as a new
  rules version, and add the inputs above to `scripts/eval/heading-values.mjs` and the mobile
  `report_cases_check.js`.
- **Status:** open. This is an extraction rule change, so it needs approval (see "Human approvals"
  below).

### R3-02: "Vitamin D3 32" is read as vitamin D 3 (High, safety)

- **Repos:** frontend `script.js:5661` and `:5664` (vitamin D regex); mobile `src/reportAnalysis.ts`
  (same rule, same output).
- **Reproduce:** `"Vitamin D3 32 ng/mL 30-100"` and `"25-OH Vitamin D3 32 ng/mL 30-100"` both give
  `Vitamin D appears around 3 ng/mL`, "Needs attention", and "1 of your 1 lab results is outside
  the lab's ranges". With `"Vitamin D2 4 ng/mL\nVitamin D3 28 ng/mL\nVitamin D, total 32 ng/mL 30-100"`
  the value read is 2, and the summary then says "0 of 1 outside" and "needs attention" at the
  same time. `"25-OH Vitamin D3 <5 ng/mL"` gives 3 instead of `<5`.
- **Cause:** `vitamin d(...)?[^\d\n]{0,24}?(\d+...)` matches zero characters and then captures the
  "3" of "D3" as the result.
- **Expected:** the D2/D3 suffix is part of the name. When a total is printed, the total is the
  value read.
- **Impact:** a normal vitamin D (32) is reported as severely low (3). The patient may be told to
  discuss a deficiency they don't have. Quest prints "VITAMIN D, 25-OH, D3 / D2 / TOTAL", so real
  reports are likely to hit this.
- **Proposed fix:** allow `d[23]?` in the name, prefer a "total" row, and refuse to read a single
  digit that touches the letter D. Release as a new rules version with regression cases on web
  and mobile.
- **Status:** open. Needs approval as for R3-01.

### R3-03: A date in brackets is read as the reference range (Medium, safety and wording)

- **Repos:** frontend and mobile (same output).
- **Reproduce:** `"Previous result: Potassium 6.9 mmol/L (2025-03-01)\nPotassium 4.2 mmol/L 3.5-5.1"`.
- **Actual:** the result read is the old value 6.9 (`rangeText: "2025-03"`), labelled
  `status: "below"` with "far" set, so the patient sees "Far below the lab's range" for a high
  potassium. The current 4.2 is ignored. Urgency is still "urgent" (the danger check uses the
  value), so the error leans towards caution, but the explanation is wrong.
- **Expected:** dates are never ranges. When an earlier result and a current result appear, the
  current one is used, and the earlier one is shown as history or the result is marked uncertain.
- **Status:** open. Needs approval.

### R3-04: A flag with no value disappears behind "all within range" (High, safety)

- **Repos:** frontend and mobile.
- **Reproduce:** `"Potassium HH\nSodium 140 mmol/L 135-145"`, `"Potassium CRITICAL\nSodium 140 ..."`,
  `"LDL cholesterol H\nHDL 52 mg/dL >40"`.
- **Actual:** "Your lab results are within the lab's ranges. All 1 results are inside the ranges."
  The critical flag is dropped without any notice.
- **Expected:** a test that has an abnormal or critical flag but no readable value is shown as
  "flagged by the lab, value not read, check with your doctor". Any reassuring headline is
  suppressed. An `HH` or `CRITICAL` flag should be at least "contact your doctor today", but the
  clinician must decide that.
- **Status:** open. This touches urgency, so it needs clinical review.

### R3-05: The pause switch did not stop server-side explanations (Medium, safety control). FIXED in this PR

- **Repo:** backend `app/api/routes/reports.py` `analyze_report`. This function also serves
  `POST /analyze-report` in `app/api/routes/mvp.py`.
- **Before:** with `CAREWISE_REPORT_EXPLANATIONS_PAUSED=true`, `/features` reported
  `report_explanations: false`, but `POST /reports/{id}/analyze` still returned 200 and saved a new
  explanation. The website calls that endpoint for uploaded reports (`script.js:7278`), and so
  does the phone app (`src/apiClient.ts:335`). Older app versions and direct API calls ignore the
  flag entirely.
- **After:** while the switch is on, both endpoints return 503 with a plain "paused" message. No
  analysis row is written, and the saved report stays downloadable. With the switch off, nothing
  changes.
- **Test:** `tests/api/test_explanations_pause.py`. It fails on the old code (`assert 200 == 503`)
  and passes with the fix. Full suite: 121 passed; `ruff check .` is clean.
- **Not changed:** no clinical rule, threshold or wording in an explanation.

### R3-06: The website ignores the pause switch when it can't reach the server (Medium)

- **Repo:** frontend `script.js:3498`. If `/features` fails, `backendFeatures = {}`, so
  `report_explanations` is undefined and explanations run on the device. When the API is down or
  waking up (Render free tier), the pause cannot take effect on the website.
- **Comparison:** the phone app fails closed. It shows nothing until it has checked the switch at
  least once, and then uses the last known value (`App.tsx:155-173`). The two platforms behave
  differently.
- **Proposed fix:** do the same on the website: remember the last answer in `localStorage`, and
  treat "never checked" as "paused" for explanations.
- **Status:** open. Low risk, but I can't push to the frontend from here.

## Suspected risks (not confirmed as bugs)

- **R3-07, reminder timing:** medicine reminder calls are sent by a GitHub Actions schedule set to
  `*/5 * * * *` (`.github/workflows/scheduled-jobs.yml`). GitHub runs scheduled jobs on a
  best-effort basis: runs are often delayed, sometimes skipped at busy times, and schedules turn
  off after 60 days without repository activity. Reminders could arrive late or not at all.
  Check the run history, or move the job to a Render cron job.
- **R3-08, old values trigger urgency:** an earlier critical value printed next to a normal current
  value makes the whole report "urgent" (see R3-03). This errs on the side of caution, but it can
  alarm people.
- **R3-09, OCR decimal slips:** "Potassium 42" and "Sodium 1.40" are treated as danger values.
  Showing "please confirm this number" is safer than a definite alarm; the clinician should decide.
- **Security assessment items still open** (from `docs/security-assessment-2026-10-22.md`, not
  re-tested here because they are dashboard or legal actions): H2 (database open to `0.0.0.0/0`),
  M1 (plain-text health columns), M2 (single encryption key), M3 (no BAAs).

## Previous findings rechecked

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Test names taking a neighbour's value | **Partially fixed.** Heading and list cases are fixed, but a blank result still takes the range's number (R3-01) | `heading-values.mjs` 16/16 pass; R3-01 |
| 2 | Vitamin D extraction | **Partially fixed.** "25-hydroxy" with no value is fixed; "D3 32" reads 3 (R3-02) | probes above |
| 3 | Units and decimals | **Verified** for decimal commas (`13,5`), g/L and mmol/L glucose. OCR slips raise an alarm instead of asking (R3-09) | probes |
| 4 | Missing or uncertain ranges | **Still broken** where the value is missing (R3-01). A missing range uses the "general guide", which is labelled | probes |
| 5 | Patient-confirmed photo corrections | **Untested** (needs a browser photo flow) | n/a |
| 6 | Urgency and emergency symptoms | **Verified** on 34 pinned cases | `safety-cases.mjs` 34/34 |
| 7 | Denied vs current symptoms | **Verified.** "denies chest pain", "History of stroke" and "No chest pain. Currently has severe shortness of breath" are all handled correctly | probes |
| 8 | Source-line traceability | **Untested** this round | n/a |
| 9 | Doctor brief correctness | **Untested** this round | n/a |
| 10 | Website and mobile parity | **Verified the two match**, including the same R3-01 to R3-04 bugs. Both on rules `2026-10-20.5`. Pause handling differs (R3-06) | probes run on both |
| 11 | Privacy disclosures vs behaviour | **Requires review.** Not re-audited this round | n/a |
| 12 | Account isolation | **Verified by existing tests** (cross-account and cross-clinic) | backend suite 121 pass |
| 13 | DocBridge clinician vs front desk | **Verified by existing tests** | `test_docbridge.py::test_approved_content_is_locked_and_front_desk_cannot_decide`, `test_team_roles_reject_audit_and_manual_review` |
| 14 | Synthetic-only clinic safeguards | **Verified in code.** Emailed labs need `DEID`, codes are REF-only, Q&A is off by default and also needs `patient_qa_safety_verified` | `app/api/routes/inbound.py`, `health.py` |
| 15 | Patient link expiry, replacement and revocation | **Verified by existing tests** | `test_clinician_can_revoke_or_replace_a_patient_link`, `test_patient_link_stops_working_when_it_expires`, `test_turned_off_or_expired_links_stop_working` |
| 16 | Notification and reminder reliability | **Partially verified.** Logic tests pass; scheduling is a risk (R3-07) | `test_reminders.py` |
| 17 | Accessibility fixes | **Untested** this round | n/a |
| 18 | Protected release tags and evidence | **Verified.** `docs/clinical-validation/` is byte-identical to tag `clinical-review-candidate-2026-10-20.2`. The `.5` pack SHA-256 `b0e1ae90…b23e` matches `docs/releases/rules-2026-10-20.5.md` | `git diff` (0 lines), `sha256sum` |

Round 2 optional finding: `passed_safety_check` now rejects `{"safe": 1}` (`app/services/patient_qa.py:200`). Verified.

## Tests run

- Backend: `python -m pytest -q` gives 121 passed (119 before this PR, plus 2 new). `ruff check .` is clean.
- Frontend: `scripts/eval/heading-values.mjs` 16/16, `safety-cases.mjs` 34/34, `run-eval.mjs`
  (68 PDFs, 200 tests: 100% read, value and flag accuracy). Plus 39 of my own adversarial text
  cases (listed in R3-01 to R3-04 and the table above).
- Mobile: the same adversarial cases through `src/reportAnalysis.ts` (transpiled with TypeScript in
  Node). No device builds were run, and nothing was tested on physical devices.

## Human approvals needed

1. **Clinical reviewer:** decide on the fixes for R3-01 to R3-04 (extraction rules and urgency for
   flags with no value). Each fix should ship as rules `2026-10-20.6` with a comparison over the
   160 cases, as was done for `.5`.
2. **Owner:** apply the fixes to the frontend and mobile (this reviewer can't push there). Check the
   reminder schedule history (R3-07).
3. **Security and legal:** items H2, M1, M2 and M3 from the 2026-10-22 assessment are still open.

## Release blockers

- **Website:** R3-01, R3-02 and R3-04 (wrong values or reassurance shown to patients).
- **iOS and Android:** the same extraction bugs. Device testing and store checks were not done in
  this round.
- **Clinic evaluation:** keep it synthetic-only. Q&A stays off until the real-model check is run.
- **Real patient deployment:** BAAs, H2, clinical sign-off on rules `.5` and later, and R3-01 to R3-04.

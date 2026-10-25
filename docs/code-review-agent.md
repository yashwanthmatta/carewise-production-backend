# Code review agent register

Statuses: OPEN · FIX IN PROGRESS · PR CREATED · VERIFIED FIXED · NEEDS HUMAN REVIEW · BLOCKED.
"VERIFIED FIXED" always has test or tool evidence next to it. All checks use synthetic data only.

Most findings are already tracked, with evidence, in:
- `docs/code-review-recheck.md`: the main register (R-, N-, S-, P-, M-, L- rows).
- `docs/code-review-round-3.md` and `docs/security-assessment-2026-10-22.md`.

This file lists only findings that those documents don't track, so each finding has one home.

Last run: 2026-10-25, backend `main` @ `c3bc075`.

| ID | Repo | File | Severity | Status | PR |
|---|---|---|---|---|---|
| CR-008 | backend | `app/services/deidentify.py` `deidentify_text` | Low | PR CREATED | see the PR for branch `claude/agent-reviewer` |
| CR-004 | backend | `app/api/routes/inbound.py` `process_message` (sender check) | Medium | OPEN | — |
| CR-009 | backend | `app/api/routes/inbound.py` `process_message` (PDF content) | Low | OPEN | — |
| CR-013 | frontend + mobile | `script.js` `readLabPanel`/`readLabMeasure`; `src/labPanel.ts`, `src/reportAnalysis.ts` (rules .6 branches) | High | NEEDS HUMAN REVIEW | website #114, app #46 (review comments posted) |

## CR-008 The training export's de-identification missed opening names and some dates

- **Reproduction:** on `c3bc075`, `deidentify_text("Maria Lopez, your A1c is 7.2. Seen on 2026/10/03, back Oct 3.")` returns the text unchanged. This function cleans the DocBridge training export (`clinics.py` `training_pairs_export`) and the patient question before it goes to the AI.
- **Expected:** the name and the full or partial dates are removed, and lab names and values are kept.
- **Fix:**
  - `YYYY/MM/DD` keeps only the year.
  - A day and month with no year ("Oct 3", "3rd October") becomes `[DATE]`. "May" must be capitalised, so "may" before a number is left alone.
  - A letter opening "First Last, your/you" becomes `[NAME],`. Common lab words (Total, Vitamin, Fasting, Blood, …) are skipped.
- **Evidence:**
  - `tests/api/test_draft_edits.py::test_deidentify_catches_opening_names_and_dates_without_a_year` fails on `c3bc075` (`assert 'Maria' not in …`) and passes with the fix.
  - Full suite: 142 passed. `ruff check .` clean.
  - The test also checks that "Total Cholesterol, your level is 210 mg/dL.", "Vitamin D, your level is 18 ng/mL." and "Your LDL may 2 points rise." are left unchanged.
- **Remaining risk:**
  - A lone first name in the middle of a sentence ("for Jose") is still not caught.
  - The hand review of each clinic's first export is described in the module but not enforced in code. Enforcing it needs an owner decision.
- **Clinical impact:** none. No explanation, threshold or urgency rule changes.

## CR-004 Email intake trusts the From header

- **Problem:** on `c3bc075`, a message is accepted when its `From` address belongs to a team member. No SPF or DKIM result is checked (no `spf`, `dkim` or `verdict` in `inbound.py`). Someone who knows a clinic's intake address and a team member's email can put a PDF in that clinic's inbox.
- **Suggested fix:** require the email provider's SPF/DKIM pass (SendGrid `SPF`/`dkim` form fields; SES `receipt.spfVerdict`/`dkimVerdict`), and let owners rotate the intake code.
- **Needs:** which inbound provider production uses. Checking the wrong field would drop every real email.

## CR-009 Nothing checks that an emailed PDF is really de-identified

- **Problem:** the pilot rule (de-identified labs only) rests on "DEID" in the subject.
- **Suggested fix:** run the `deidentify.py` patterns on the extracted text and mark the lab "possible identifiers" so the clinician sees a warning. This needs a matching DocBridge screen change in the website.

## CR-013 Rules .6 reads a lab's explanatory sentence as a second result

- **Found:** 2026-10-25, while reviewing website #114 and app #46 (not merged). Live rules `.5` are not affected.
- **Reproduction (synthetic):**
  - `"Potassium 4.1 mmol/L 3.5-5.1\nPotassium above 5.5 mmol/L may need follow-up."` gives potassium 5.5 "above" on `.6`, against 4.1 "within" on `.5`.
  - `"LDL cholesterol 98 mg/dL <100\nLDL cholesterol above 160 mg/dL is considered high."` gives LDL 160 on `.6`, against 98 on `.5`.
  - The website and the app give the same output.
- **Patient impact:** a number the lab never measured for this person is shown as their result. It errs toward alarm, but it is still a false value.
- **Suggested fix:** count a repeat only when the line looks like a result row. Reject lines with words between the test name and the number (above, below, level, is, …), and lines that go on as a sentence after the unit.
- **Also seen:** `yyyy-mm` and `dd-mm-yyyy` dates are still read as the range, and `Sodium 14O` is still read as 14.
- **Independently confirmed:** another reviewer session recorded the same regression as R6-REG in `docs/code-review-fix-check.md`, with an A1C footnote example.
- **Why human review:** it's a clinically consequential rules change, so the owner and the clinical reviewer decide. This reviewer doesn't push to those branches.

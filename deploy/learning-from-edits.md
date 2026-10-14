# Learning from doctor edits (DocBridge)

Every time a clinician saves or approves a draft, the API stores a `draft_edits` row:
the draft as generated, the clinician's version, which sections changed, a word-level
edit distance worked out on the server, whether it was approved with no edits, and the
`model_version` / `prompt_version` that produced the draft. Text is encrypted and is
deleted with its lab (clinic retention or account deletion).

Today's drafts are rule-based (`docbridge-rules-v1`, `docbridge-draft-v1`). When drafting
moves to an LLM, the browser or server sends the new versions on draft creation and the
same capture keeps working. Add each new version to `model_versions`; a person changes
its status (`canary` / `prod` / `retired`). Nothing is promoted automatically.

## Endpoints

- `GET /clinics/{id}/edit-metrics` (any member): per model version and ISO week, the
  approvals, approval-without-edit rate, mean edit distance and saves, plus totals.
- `GET /clinics/{id}/training-pairs.jsonl` (owner only, logged): one line per edit,
  `{prompt: {lab_year, markers, tone}, chosen: doctor's version, rejected: original
  draft, zero_edit_approval, edited_sections, edit_distance, model_version, ...}`, passed
  through `app/services/deidentify.py`.

## De-identification

`deidentify_text` removes known names (patient reference, clinic, team members),
emails, phone numbers, record and account numbers, dates of birth, name and address
lines, street addresses, ZIP codes, greeting names, and reduces full dates to the year.
Lab names, values, units, ranges and flags are kept. It is a first pass, not a
guarantee: review the first export of every clinic by hand, because rare conditions
with exact values can still identify someone.

## Before any training on patient data

1. BAA signed with the model provider, zero data retention confirmed in writing.
2. De-identification pass on every export, and the manual review above.
3. Phase 1 (now): weekly read of the pairs, grouped by section, to turn repeated edits
   into prompt changes that a person reviews; bump `prompt_version`.
4. Phase 2 (about 500+ pairs): DPO with chosen = edited, rejected = original; zero-edit
   approvals as low-weight positives. Evaluate on held-out pairs (lower edit distance
   than prod), canary on 10% of drafts, and a person signs off before promotion.
5. Never: learning in the request path, cross-clinic learning without consent and legal
   review, or sending any unapproved model output to a patient.

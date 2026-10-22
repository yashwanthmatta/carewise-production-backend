# Security assessment: stored health data and access control

Date: 2026-10-22. Prepared by the engineering team for an independent security reviewer.
Status: **draft for review.** Apart from the staff-role fix in section 2 (H1), nothing here has
been changed in production. No data migration has been run.

Scope: the consumer app's saved data (accounts, profiles, reports, results, lab tracker,
reminders, doctor links), DocBridge (clinic) data, and the hosting setup on Render. Method:
code review of `app/models`, `app/core`, `app/api/routes`, `app/services`; automated
cross-account tests; Render API configuration read-out; Render public documentation.

## 1. Highest risks

| ID | Risk | Severity | Status |
|---|---|---|---|
| H1 | A staff role (clinician/admin) took effect at sign-up before the email was verified. Someone who registered a listed staff address they do not own could read every patient profile. | High | **Fixed in this PR**, with a test that fails on the old code |
| H2 | The production database accepts connections from any internet address (`ipAllowList: 0.0.0.0/0`). It still needs the password and TLS, but a leaked database URL would be usable from anywhere. | High | **Owner action**: restrict in the Render dashboard (section 6) |
| M1 | For people who save to an account, results summaries, lab tracker values, care-plan content and some profile fields are stored as plain database columns (inventory in section 3). Render encrypts the disk and backups, but anyone with database read access sees them. | Medium | Design below; not executed |
| M2 | All field encryption uses one static key held in a Render environment variable. There is no key version, rotation or managed key service. If the configured value is not a valid Fernet key, it is turned into one with a single SHA-256 hash, with no key-derivation function. | Medium | Design below |
| M3 | The Render workspace is not HIPAA-enabled, so there is no Business Associate Agreement. The same applies to AWS S3, Anthropic and the email provider until agreements are signed. | Medium (legal) | Already pilot-only with de-identified/sample data; legal review |
| M4 | Global clinician/admin roles can open **any** patient profile; access isn't limited to patients that person cares for. Two-step sign-in isn't required for staff. | Medium | Recommendation (section 6) |
| L1 | The audit log stored uploaded file names, which people sometimes name after the patient. | Low | **Fixed** (new entries no longer include the name; older entries keep it until removed) |
| L2 | Database has no high availability, a 1 GB disk with autoscaling off, and point-in-time recovery of 3 days (Hobby) or 7 days (Professional+). | Low (availability) | Recommendation |

## 2. H1 fix (in this PR)

`app/core/security.py` `get_current_user`: an elevated role now needs **both** the staff list
entry and `email_verified == "true"`. Until the address is verified the account acts as a
patient; the stored role is kept, so the person gets their role straight after verifying.

- Test: `tests/api/test_staff_roles.py::test_staff_role_waits_for_email_verification`. It fails on the
  previous code (`assert 'clinician' == 'patient'`) and passes now. Full suite: 107 passed.
- Impact: an existing staff account whose email isn't verified loses staff access until it
  verifies. DocBridge doctors aren't affected; their clinic roles are separate from these global roles.
- Needs: email delivery working in production, so staff can receive the verification link.

## 3. Sensitive data inventory

"App-encrypted" means encrypted by our code (Fernet) before it reaches the database. Every
column is also covered by Render's disk encryption (AES-256, including backups, per Render's
documentation).

| Table | Column(s) | Contents | App-encrypted |
|---|---|---|---|
| users | email, password_hash, encrypted_totp_secret | account | email **no** (needed for login); password hashed; TOTP secret yes |
| patient_profiles | encrypted_name, encrypted_date_of_birth, encrypted_conditions, encrypted_allergies | identity, history | yes |
| patient_profiles | sex_at_birth, location_region, insurance_status | demographics | **no** |
| medications | encrypted_name/dose/timing/notes | medicines | yes (refill_date no) |
| intakes | encrypted_symptom_text | symptoms | yes |
| intakes | goals_json, diet_style, activity_level | goals | **no** |
| care_plans | risk_level, emergency_flags_json, matched_conditions_json, recommendation_json, clinician_note | health assessment | **no** |
| report_uploads | encrypted_report_text | full report text | yes |
| report_uploads | file_name | file name | **no** |
| report files (S3) | object | original PDF/photo | S3 server-side AES-256 (not app-level) |
| report_analyses | risk_level, summary_json, recommendations_json | results, values, explanations | **no** |
| lab_trends | test_name, value, unit, observed_on, flag | lab tracker | **no** (encrypted_notes yes) |
| doctor_shares | encrypted_label, encrypted_snapshot; token_hash | shared summary | yes; token stored only as a hash |
| medicine_reminders | encrypted person/label/phone/name | reminders | yes |
| product_feedback, early_access | comments, email | feedback | yes |
| lab_packets (DocBridge) | encrypted patient_ref, markers, summary, questions, draft, source text | clinic labs | yes; patient link stored as a hash |
| draft_edits, patient_questions (DocBridge) | encrypted original/edited text, question/answer | doctor edits | yes (edited_sections, citations no) |
| audit_events | action, metadata_json | who did what | no; checked: only counts and roles, no values (file names no longer recorded) |
| notification_preferences | device_token | push token | **no** |

The plaintext health columns that matter most are `report_analyses.summary_json` and
`recommendations_json`, `lab_trends.test_name/value/unit/flag`, the `care_plans` JSON and
`clinician_note`, and `intakes.goals_json`.

## 4. What was verified as working

- **No cross-account access** (automated tests): reports (list, download, analyses, edit text,
  analyze), lab trends, medications, care plans, doctor links, reminders (new test: list, edit,
  mark taken, call consent, delete), and every DocBridge route against other clinics.
- **Doctor links and DocBridge patient links:** 256-bit random tokens (`secrets.token_urlsafe(32)`)
  stored only as hashes. They expire, can be revoked, and viewing them is rate-limited (60 per hour).
- **Record IDs** are random UUID4s, so they can't be guessed in sequence. Access is still checked on every request.
- **Doctor demo (website):** runs entirely in the browser with a made-up clinic. The browser test shows zero
  server calls, and it can't reach real clinician or patient workflows.
- **"Show the line from your report":** matches only against the report text currently on
  screen, so it can't show another report's line. It shows nothing unless exactly one line matches.
- **Logs:** spot check found no report text, values or summaries in log calls.
- **Production configuration guard:** the app refuses to start in production with placeholder
  `DATABASE_URL`, `JWT_SECRET` or `FIELD_ENCRYPTION_KEY`.

## 5. Proposed field-encryption design (not executed)

### Which data

Encrypt `report_analyses.summary_json`, `recommendations_json`; `lab_trends.test_name`,
`value`, `unit`, `flag`; `care_plans.emergency_flags_json`, `matched_conditions_json`,
`recommendation_json`, `clinician_note`; `intakes.goals_json`; `report_uploads.file_name`;
`patient_profiles.sex_at_birth`, `insurance_status`. Keep `observed_on`, `risk_level`,
`created_at` and IDs in plain text: they are used for ordering and counts and reveal little on their own.
`risk_level` is debatable, so the reviewer should decide.

### Effect on features

No SQL query filters or sorts on the columns above. Lab trends are ordered by `observed_on`,
which stays plain, and trend charts and comparisons are built in the app after reading. So
trends, comparisons, the privacy export and account deletion keep working. They decrypt in
Python, as the already-encrypted fields do. Future server-side search or filtering on lab values
would need a separate design (for example a keyed hash for exact match). Range queries on
encrypted values aren't possible.

### Keys

1. Make sure the production key is a real 32-byte Fernet key, not a passphrase (no change
   to stored data; check in the Render dashboard).
2. Add key versioning with `cryptography`'s `MultiFernet`. `FIELD_ENCRYPTION_KEYS` lists the new key first,
   then old keys; encryption uses the first key, and decryption tries all of them. Rotation means adding a new key and
   re-encrypting in the background, then removing the old key.
3. Later, before real patient data: envelope encryption with a managed key service such as AWS KMS, with the data key
   cached in memory. This needs a BAA-covered account.

Use only the `cryptography` library's authenticated encryption (Fernet: AES-128-CBC with an
HMAC-SHA256 check). We write no cryptographic code of our own.

### Migration steps (each step reversible until step 6)

1. **Add new columns** (`encrypted_summary_json`, and so on). The old columns stay.
2. **Dual write:** the code writes both old and new columns; reads prefer the new column and fall back to the old.
3. **Backfill** in small batches (for example 200 rows) inside transactions. The job is resumable: it
   records the last ID done and is safe to re-run. For each row it decrypts the new value and
   compares a SHA-256 of it with the old value before committing (integrity check).
4. **Verify:** row counts match; zero mismatches; the privacy export of a test account is identical
   before and after; the app test suite passes against a copy of production restored with point-in-time recovery.
5. **Read new only** (old columns still filled), for at least one full backup window.
6. **Clear old columns** (set to empty). This is the point of no return for the old copies, so do
   it in its own release after the reviewer signs off.
7. **Drop old columns** in a later release.

Run steps 3–4 first on a synthetic-data copy, then on a restored copy of production, and only then on production.

### Downtime and data loss risks

- **Downtime:** none expected. Columns are added online, and the backfill runs in small batches
  while the app serves traffic.
- **Data loss:** the main risk is losing or mistyping the key, which makes new columns
  unreadable. Mitigations: the old columns are kept until step 6, the key is backed up outside Render before
  starting, and there's an integrity check per row.
- **Rollback:** before step 6, switch reads back to the old columns (a one-line config flag) and
  drop the new columns.

### Existing backups and copies

Point-in-time recovery keeps earlier database states for 3 or 7 days, and manual exports are kept 7 days
(Render documentation). Plaintext copies therefore age out on their own once that window has
passed after step 6. Manual exports, local dumps and any CSVs made from the database must be found
and deleted by hand. Make no new plaintext exports during the migration.

## 6. Owner actions and reviewer decisions

1. **H2:** in Render → `carewise-postgres` → Networking, remove the `0.0.0.0/0` entry so only
   Render services connect over the internal network. First check that nothing outside Render
   (a laptop or admin tool) still needs access; if one does, add only that address.
2. Confirm the production `FIELD_ENCRYPTION_KEY` is a generated Fernet key, and keep an
   offline backup of it.
3. Decide whether to require two-step sign-in for staff roles, and whether clinician access
   should be limited to assigned patients (M4).
4. Approve or change the field list and migration plan in section 5 before any code that
   writes data is merged.
5. Legal: BAAs (Render HIPAA workspace on Scale/Enterprise plans, AWS, Anthropic, email
   provider) before any real patient data. Until then, keep DocBridge pilot-only with
   de-identified or sample data.
6. Monitoring: confirm error alerts reach a person, and test the report-explanations pause
   switch (`CAREWISE_REPORT_EXPLANATIONS_PAUSED`) in production once.

## 7. Clinical review pack integrity

`docs/clinical-validation/` in the website repo is byte-for-byte identical to the protected tag
`clinical-review-candidate-2026-10-20.2` (SHA-256: blinded-cases `923d6628…74b5f`,
validation-cases `bcbc558f…53d72`, blind-key `5db6654b…e4d09`). No commits touched it after
the tag. The live app runs rules `2026-10-20.3`, which adds two defect fixes listed in
`docs/clinical-rules-for-review.md`; the reviewer should check those alongside the `.2` pack.

## Sources

- Render Postgres recovery and backups: https://render.com/docs/postgresql-backups
- HIPAA on Render (BAA, HIPAA-enabled workspaces, disk encryption): https://render.com/docs/hipaa-compliance
- Building HIPAA-compliant apps on Render: https://render.com/docs/hipaa-best-practices
- How Render handles secrets and environment variables: https://render.com/articles/how-render-handles-secrets-and-environment-variables

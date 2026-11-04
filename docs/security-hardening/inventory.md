# Sensitive data inventory and traceability matrix

Last updated: 2026-11-02. Built from the code in this repository (`app/models/carewise.py`, `app/core`, `app/api/routes`, `app/services`), the frontend and mobile repositories, and `docs/security-assessment-2026-10-22.md`. No patient record or secret value was read to produce it.

**Encryption terms used below:**
- **"App-encrypted"** means our code encrypts the value before it reaches the database: Fernet, i.e. AES-128-CBC with an HMAC-SHA256 tag, from the `cryptography` library.
- Since this change, every new value is stored as `ftenc:<key id>:<token>`, so each value names the key that encrypted it (see `key-rotation.md`).
- Render's disk encryption is a separate layer that covers every column. **It is not counted as protection here**, because anyone with database read access still sees the values.

## 1. Where report content travels

| Step | Website | Phone app | Backend |
|---|---|---|---|
| Choose a file | Stays in the browser | Stays on the phone | — |
| Read text (PDF, photo OCR) | In the browser (pdf.js, Tesseract). Not uploaded. | — | `/reports/upload` (account users) stores the file in S3 or local storage, plus the text app-encrypted |
| Explain results | In the browser (rules engine). Not uploaded. | In the app | `/reports/{id}/analyze` → `report_analyses` |
| AI wording (optional) | Only if the person asks the assistant | — | OpenAI Responses API (`app/services/storage.py`), when `OPENAI_API_KEY` is set |
| Save to account | Only when the person signs in and saves | Same | Database (this inventory) |
| Share with a doctor | Only when the person creates a link | — | `doctor_shares.encrypted_snapshot`. The token is stored only as a hash. |
| Delete | `DELETE /privacy/me` | Same | Rows deleted, stored files deleted; backups expire on Render's schedule |

**Device-first by default:** report explanation already happens on the device. The server only sees report content when a signed-in person chooses to save, share, or use the AI assistant. Section 4 lists the external processors.

## 2. Traceability matrix: account-side health data

Status key:
- **Already** — encrypted before this change.
- **Now** — encrypted by this change via `EncryptedText`. New writes are encrypted immediately. Existing rows stay readable as plaintext until `scripts/security/encrypt_fields.py --apply` runs.
- **Plain** — still stored in plaintext; the reason is given.

| Table.column | Contents | Protection | Status | Who can read (API) | Retention / deletion |
|---|---|---|---|---|---|
| users.email | Sign-in email | Plain: needed for login lookup | Plain | Owner; staff role checks | Deleted by `DELETE /privacy/me` |
| users.password_hash | Password | pbkdf2-sha256 hash | — | Never returned | Same |
| users.encrypted_totp_secret | Two-step secret | App-encrypted | Already | Never returned | Same |
| patient_profiles.encrypted_name, encrypted_date_of_birth, encrypted_conditions, encrypted_allergies | Identity and history | App-encrypted | Already | Owner; clinician/admin (see access-control gap H-4) | Same |
| patient_profiles.sex_at_birth, insurance_status | Demographics | App-encrypted | **Now** | Same | Same |
| patient_profiles.location_region | Region | App-encrypted; its index was dropped | **Now** | Same | Same |
| medications.encrypted_name/dose/timing/notes | Medicines | App-encrypted | Already | Owner + staff | Same |
| medications.refill_date | Date | Plain: date only, no medicine attached when read alone | Plain (documented) | Same | Same |
| intakes.encrypted_symptom_text | Symptoms | App-encrypted | Already | Owner + staff | Same |
| intakes.goals_json, diet_style, activity_level | Goals and lifestyle | App-encrypted | **Now** | Same | Same |
| care_plans.emergency_flags_json, matched_conditions_json, recommendation_json, clinician_note | Care plan | App-encrypted | **Now** | Same | Same |
| care_plans.risk_level, status | Triage category (routine / clinician_review / emergency) and workflow state | Plain: coarse category kept for review queues and indexes | Plain (documented; candidate for a later pass) | Same | Same |
| report_uploads.encrypted_report_text | Full report text | App-encrypted | Already | Owner + staff | Same, plus the stored file |
| report_uploads.file_name | File name (people name files after patients) | App-encrypted | **Now** | Same | Same |
| report files (S3/local) | Original PDF/photo | S3 server-side AES-256; DocBridge email PDFs app-encrypted with `encrypt_bytes` | Partial | Via signed access only | Deleted with the report |
| report_analyses.summary_json, recommendations_json | Results, values, explanations | App-encrypted | **Now** | Owner + staff | Same |
| report_analyses.risk_level | Triage category | Plain (as care_plans) | Plain (documented) | Same | Same |
| lab_trends.test_name, value, unit, flag | Lab tracker | App-encrypted. Values are stored as the exact text, so precision is kept. Three indexes dropped. | **Now** | Owner + staff | Same |
| lab_trends.observed_on | Date | Plain: used to sort the tracker in SQL | Plain (documented) | Same | Same |
| lab_trends.encrypted_notes | Notes | App-encrypted | Already | Same | Same |
| doctor_shares.encrypted_label, encrypted_snapshot | Shared summary | App-encrypted; token stored as a hash | Already | Link holder (anonymous) until expiry or turn-off | Deleted with the account; expires |
| medicine_reminders.encrypted_person/label/phone/caller_name | Reminders | App-encrypted | Already | Owner | Same |
| medicine_reminders.times, days, timezone | Schedule | Plain: the scheduler queries it | Plain (documented) | Owner | Same |
| data_deletion_requests.reason | Why the person is leaving | App-encrypted | **Now** | Admin | Kept as the record of the request |
| data_deletion_requests.email | Contact for the request | Plain: needed to confirm deletion | Plain (documented) | Admin | Same |
| product_feedback.encrypted_comment; early_access.encrypted_email, encrypted_note | Feedback | App-encrypted; email also as a hash for de-duplication | Already | Admin | — |
| audit_events.metadata_json | What happened (counts, roles, ids) | Plain. **Must not contain health content.** Lab test names were removed from it in this change. | Fixed | Admin | Retained |

## 3. DocBridge (clinic) data

| Table.column | Contents | Protection | Status |
|---|---|---|---|
| lab_packets.encrypted_patient_ref, markers, summary, questions, draft, source_text, draft_questions | Clinic lab packet | App-encrypted; the patient reference is also stored as a hash | Already |
| lab_packets.lab_date, status, approved_by_name | Workflow | Plain | Plain (documented) |
| draft_edits.encrypted_original_text, encrypted_edited_text | Doctor edits | App-encrypted | Already |
| patient_questions.encrypted_question, encrypted_answer | Patient Q&A | App-encrypted | Already |
| Packet retention | — | Deleted after the clinic's `retention_days` (30–365, default 90) by `/maintenance` | Existing |

## 4. External processors (from the code; contracts not reviewed)

| Processor | What it receives | When | Contract status |
|---|---|---|---|
| Render (hosting, PostgreSQL) | Everything stored | Always | Workspace not HIPAA-enabled; no BAA (assessment M3) |
| AWS S3 | Uploaded report files | Account users who upload | No BAA recorded |
| Anthropic (Messages API) | Help-assistant chat messages; DocBridge patient follow-up questions (only when `CAREWISE_PATIENT_QA_SAFETY_VERIFIED`) | When `ANTHROPIC_API_KEY` is set and the person uses the assistant | Written terms not reviewed here; do not assume zero retention |
| OpenAI (Responses API) | Report text or question for AI wording | Only when configured and the person uses that feature | Written terms not reviewed here. **Do not assume zero retention.** |
| Email provider (SMTP) | Email address, links | Verification, reset, notices | No BAA recorded |
| Twilio | Phone number, spoken reminder text | Phone reminders after consent | No BAA recorded |
| Stripe | Billing identity | Subscriptions | Payment data only |

## 5. Secrets and keys

| Secret | Where it lives | Notes |
|---|---|---|
| `CAREWISE_FIELD_ENCRYPTION_KEY` (key id k1) | Render environment | Kept readable by design. **Finding:** the settings helper `clean_env_value` treats the first `=` as a `NAME=value` separator, so a bare Fernet key ending in `=` would be read as empty. Production startup would refuse to run in that case (the empty value counts as missing), so it fails closed. The k1 behaviour is unchanged on purpose, because changing it could change the effective production key. |
| `CAREWISE_FIELD_ENCRYPTION_KEYS`, `CAREWISE_FIELD_ENCRYPTION_CURRENT_KEY_ID` | Render environment (new, optional) | Parsed without that helper. See `key-rotation.md`. |
| JWT secret, Stripe, Twilio, SMTP, OpenAI keys | Render environment | Never in source control. `scripts/generate_secrets.py` makes new ones. |

## 6. Gaps carried to other workstreams

1. **Database open to all internet addresses** (assessment H2). Needs an owner action in the Render dashboard; see `render-network-lockdown.md` (to be written).
2. **Clinician and admin global roles can open any patient profile** (`app/services/access_control.py`). Workstream 4.
3. **Two-step sign-in is optional for staff.** Workstream 5.
4. **Your Data page.** The export and deletion APIs exist (`/privacy/me/export`, `DELETE /privacy/me`); the patient-facing page is workstream 6.

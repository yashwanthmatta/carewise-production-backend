# Encrypting the remaining plaintext health fields

## What changes

These columns now use `EncryptedText`. The SQLAlchemy type encrypts before writing and decrypts after reading:
- report_analyses.summary_json, recommendations_json
- care_plans.emergency_flags_json, matched_conditions_json, recommendation_json, clinician_note
- lab_trends.test_name, value, unit, flag
- intakes.goals_json, diet_style, activity_level
- patient_profiles.sex_at_birth, location_region, insurance_status
- report_uploads.file_name
- data_deletion_requests.reason

Routes and services are unchanged. They read and write ordinary strings, and the column type does the work.

## Storage design and tradeoffs

| Use of the value | Decision |
|---|---|
| **Precision of lab values** | Values were already strings (`"5.40"`). They are encrypted as the exact text, so no number is reformatted. A test checks `"5.40"` round-trips exactly. |
| **Sorting** | The tracker sorts by `observed_on` and `created_at`. Both stay plaintext. Nothing sorts by an encrypted column. |
| **Filtering and search** | No query filters on these columns (checked with grep across `app/`). The indexes on lab test name, lab flag and region were dropped, because ciphertext cannot be searched. If a search is ever needed, add an HMAC "blind index" column, never a plaintext copy. |
| **Trends and calculations** | Done in Python after the authorised read, as before. |
| **Exports** | `/privacy/me/export` reads through the model, so it returns plaintext only to the authorised owner, as before. |
| **Report reconstruction and doctor briefs** | Unchanged: they read the same attributes. |
| **Kept plaintext on purpose** | `risk_level` (coarse triage category, used for review queues), `observed_on`, reminder schedule times, `medications.refill_date`, deletion-request email. Each is listed with its reason in `inventory.md`. |

## Rollout (no irreversible step in the first deployment)

1. **Deploy the code and migration `0023_encrypt_health_fields`.**
   - The migration only widens columns to TEXT and drops three unusable indexes. No data changes.
   - The new code reads plaintext rows as they are and writes new rows encrypted.
   - Rows written by the new code are unreadable to the previous release. See Rollback before going back a release.
2. **Report:** `PYTHONPATH=. python scripts/security/encrypt_fields.py`
   - It prints per-column counts: `plaintext`, `legacy`, `k1`, `empty`.
   - It never prints a value.
3. **Backfill (owner approval needed for production):**
   - Take a database backup first.
   - Then run `PYTHONPATH=. python scripts/security/encrypt_fields.py --apply --checkpoint /tmp/encrypt-fields.json`.
   - It is idempotent: values already under the current key are skipped.
   - It works in batches of 200 rows by default, one transaction per batch.
   - The checkpoint file records the last finished id per table, so an interrupted run resumes after the last finished batch. A half-finished batch is rolled back.
   - Each new value is decrypted and compared to the original before it is written; a mismatch stops the run.
   - The exit code is 1 if any value could not be read. Those values are counted and left untouched.
4. **Verify:**
   - Run step 2 again; `not_yet_current` must be 0.
   - Spot-check report history, lab tracker, care plan and doctor links in the app.

## Rollback

| Situation | Action |
|---|---|
| Before the backfill, new code misbehaves | Redeploy the previous release. Rows written by the new code in the meantime are encrypted and the old code would show ciphertext, so first run the decrypt step below on those rows. |
| After the backfill | 1. `PYTHONPATH=. python scripts/security/encrypt_fields.py --apply --to-plaintext --i-understand --checkpoint /tmp/back.json`. This writes plaintext back into the EncryptedText columns only; `encrypted_*` columns stay as they are, because every release reads them. 2. `alembic downgrade 0022_clinic_visit_settings`. 3. Redeploy the previous release. |
| Data damaged | Restore the backup taken before step 3. |

## Evidence

- **Unit and API tests:** `tests/api/test_field_encryption.py`, 26 tests, all passing. The full suite passes (191 tests).
- **Local PostgreSQL 16 staging check, 2026-11-02, synthetic data only** (`/tmp` script; summarised here):
  1. Built the schema at 0022 and inserted 250 lab rows plus one profile in the old plaintext form.
  2. Upgraded to 0023.
  3. Report: `{'plaintext': 250}`.
  4. Apply in batches of 100: exit 0, `not_yet_current` 0.
  5. All raw rows start `ftenc:k1:`. All 250 values read back exactly (`0.00` … `2.49`), and the region reads `US-CA`.
  6. Rotated to k2: `not_yet_current` 0; the key ids present were only `k2` and `empty`.
  7. Rolled back with `--to-plaintext`, then `alembic downgrade`. The row reads `('1.23', 'Synthetic A1C')` in plaintext again.
- **SQLite:** `alembic upgrade → downgrade → upgrade` passes.

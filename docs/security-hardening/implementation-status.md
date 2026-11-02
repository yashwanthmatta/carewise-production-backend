# Security hardening: implementation status

**Statuses:**
- **COMPLETE:** implemented, tested and verified, and any approval it needs has been given.
- **PARTIALLY COMPLETE:** code merged or in review, but a remaining step (production run, approval, review) is open.
- **BLOCKED:** needs access or a decision that only the owner can give.
- **NOT STARTED**

Last updated: 2026-11-02.

| # | Requirement | Repo | Status | Implementation / PR | Tests and evidence | Remaining work | Approval needed | Rollback |
|---|---|---|---|---|---|---|---|---|
| 0 | Inventory and traceability matrix | backend | PARTIALLY COMPLETE | `inventory.md` (this PR) | Built from code; no patient records or secrets read | Review by an independent assessor; DocBridge workflow columns | — | n/a |
| 1 | Database network lockdown | Render | **BLOCKED** (owner dashboard action) | `render-network-lockdown.md` | Render API read on 2026-11-02: `ipAllowList 0.0.0.0/0` still present; the API is in the same region; `render.yaml` uses the internal connection string; no other database users found | Owner: confirm the internal URL, then remove `0.0.0.0/0` | Owner | Re-add the rule (instant) |
| 2 | Encrypt plaintext health fields | backend | PARTIALLY COMPLETE | `EncryptedText` on 18 columns; migration 0023 (widen and drop 4 unusable indexes); lab test names removed from audit metadata (this PR) | `test_field_encryption.py`; raw-row checks prove ciphertext at rest; `"5.40"` precision kept; full suite 191 passed; SQLite and local PostgreSQL 16 synthetic staging check (see `encryption-migration.md`) | Independent review; staging deploy; production backfill | **Owner approval** before the production backfill; independent review of the encryption design | `--to-plaintext` then `alembic downgrade`, or restore the backup |
| 3 | Versioned keys and rotation | backend | PARTIALLY COMPLETE | `app/core/crypto.py` key ring (`ftenc:<id>:`), `CAREWISE_FIELD_ENCRYPTION_KEYS` / `_CURRENT_KEY_ID` / `_KEY1_RETIRED`; `scripts/security/encrypt_fields.py` (report / apply / resume / to-plaintext) (this PR) | Rotation, early key removal, k1 retirement, interrupted resume, unreadable values left untouched; PostgreSQL rotation k1→k2 with 0 values left behind | Re-encrypting stored files (DocBridge email PDFs) under a new key; a real rotation in staging | Owner approval for a production rotation | Keep the old key configured; nothing is destroyed |
| 4 | Patient- and clinic-level access control | backend | NOT STARTED | — | — | Replace global clinician/admin access in `access_control.py` with explicit grants | Independent review | — |
| 5 | MFA for privileged staff | backend + web | NOT STARTED | TOTP two-step sign-in already exists (0016) | — | Enforcement for staff roles; recovery codes; staged rollout | Review before enforcement | — |
| 6 | Your Data privacy centre | web + backend | NOT STARTED | Export and deletion APIs exist (`/privacy/me/export`, `DELETE /privacy/me`) | — | Page, activity list, deletion flow | — | — |
| 7 | Retention, deletion, export, audit | backend | NOT STARTED | — | — | — | — | — |
| 8 | Automated security tests and monitoring | backend CI | PARTIALLY COMPLETE | Encryption and rotation tests run in Backend CI with every PR | — | Authorization matrix tests; dependency audit; weekly drift check of `ipAllowList` and key configuration | — | — |
| 9 | Privacy-safe analytics | backend + web | NOT STARTED | `usage_counters` already stores counts only | — | Document; review events | — | — |
| 10 | Legal and HIPAA readiness checklist | docs | NOT STARTED | — | — | Checklist for counsel; BAAs (Render, AWS, Anthropic, OpenAI, email, Twilio) | Licensed counsel | — |

## Findings made during this work

- **Key setting parser.** `Settings.clean_env_value` treats the first `=` as a `NAME=value` separator, so a bare Fernet key, which ends in `=`, would be read as empty. Production startup refuses an empty key, so this fails closed. The handling of k1 was left as it is, so the effective production key cannot change. New rotation keys are parsed without that helper.
- **Database URL parser.** The same helper would also break a database URL that has `?a=b` options.
- **Decryption placeholder.** `decrypt_field` used to return the text `[unreadable encrypted field]` in place of the data. It now raises, and the API answers a clear 500.

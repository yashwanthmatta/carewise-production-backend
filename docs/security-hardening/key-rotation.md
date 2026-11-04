# Field encryption keys: versions and rotation

## Design

- **Cipher:** Fernet from the `cryptography` library (AES-128-CBC with an HMAC-SHA256 tag; a fresh random IV for every value). No custom cryptography.
- **Stored form:** `ftenc:<key id>:<Fernet token>`. Every value names its key. Values written before key ids existed are bare Fernet tokens (`gAAAAA…`); they are read with k1 first, then the other keys.
- **Key ring:** comes from the environment only.
  - `CAREWISE_FIELD_ENCRYPTION_KEY` is key id **k1**, the original key. It is read exactly as before.
  - `CAREWISE_FIELD_ENCRYPTION_KEYS` holds extra keys, e.g. `k2:<fernet key>,k3:<fernet key>`. Ids are letters and digits; each key must be a valid 32-byte Fernet key.
  - `CAREWISE_FIELD_ENCRYPTION_CURRENT_KEY_ID` (default `k1`) names the key that encrypts new values.
  - `CAREWISE_FIELD_ENCRYPTION_KEY1_RETIRED=true` removes k1. Use it only after the rotation below has been verified.
- **Failure:** a value that cannot be decrypted raises `FieldDecryptionError`.
  - The API answers 500 ("Some saved information could not be read…") and logs the key id only.
  - The old behaviour returned the text `[unreadable encrypted field]` in place of the data; that is gone.
- **Startup:** malformed key settings stop production startup, and the error names the key id, never the key.

## Key lifecycle

| State | Meaning |
|---|---|
| Current | Encrypts new values; also decrypts |
| Decrypt-only | Still configured; decrypts values not yet moved |
| Retired | Removed from the ring after verification. The key material is kept offline (see Recovery). |
| Destroyed | Only by a separate, written owner decision after the backup window has passed |

**Rules:**
- Never delete or overwrite a key that any stored value or backup may still need.
- Nothing in this repository destroys a key.

## Rotation procedure (k1 → k2)

1. **Generate the key** on a trusted machine:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   Store it in the password manager as "FollowThrough field key k2".
2. **Staging:**
   - Add `CAREWISE_FIELD_ENCRYPTION_KEYS=k2:<key>` and `CAREWISE_FIELD_ENCRYPTION_CURRENT_KEY_ID=k2`, keeping `CAREWISE_FIELD_ENCRYPTION_KEY` unchanged.
   - Deploy. New writes now use k2, and old values still read.
3. **Report (changes nothing):** `PYTHONPATH=. python scripts/security/encrypt_fields.py`
   This shows counts per key id for every encrypted column.
4. **Move the values:**
   `PYTHONPATH=. python scripts/security/encrypt_fields.py --apply --checkpoint /tmp/rotate-k2.json`
   - It is resumable: if it stops, run the same command again.
   - Each new value is decrypted and compared before it is written.
   - Values that cannot be read are counted, left untouched, and make the exit code 1.
5. **Verify:**
   - Run step 3 again; `not_yet_current` must be 0, and no column may report `k1` or `legacy`.
   - Exercise the app in staging (report history, lab tracker, care plan, doctor link).
6. **Production:** repeat steps 2–5 only after the owner approves. Take a fresh database backup first.
7. **Retire k1:**
   - Wait until every backup that may contain k1 values is past the restore window you would ever use (Render point-in-time recovery: 3–7 days by plan; keep longer if you hold manual backups).
   - Then set `CAREWISE_FIELD_ENCRYPTION_KEY1_RETIRED=true` and deploy.
   - Keep k1 offline (step 1's password manager entry) in case an old backup must be restored.
8. **Record** the date, key ids and the final report output in `implementation-status.md`.

**Uploaded files** (`encrypt_bytes`, DocBridge email PDFs) are versioned the same way from now on. Files written earlier are bare tokens and stay readable while their key is configured. Re-encrypting stored files is a separate tool, still to be written, so **do not retire k1 while such files exist.** They are deleted by clinic retention (30–365 days).

## Recovery

- **A key is missing from the environment:**
  - Every value under it fails loudly (500 plus a log line naming the key id).
  - No data is changed.
  - Restore the key from the password manager; nothing needs repair.
- **A key is lost for good:**
  - Values under it cannot be recovered, by design.
  - The report in step 3 shows exactly which tables and how many values are affected.
  - Treat it as a data-loss incident.
- **A rotation is interrupted:** rerun with the same checkpoint. Values already moved are skipped.

## Testing

`tests/api/test_field_encryption.py` covers:
- the round trip and the versioned prefix
- legacy tokens
- tampered tokens and the wrong key
- unknown key ids
- no values in logs
- the key-ring validation messages (which never contain the key)
- rotation and reading old values
- removing a key too early
- retiring k1
- the tool moving every value
- interrupted and resumed runs
- unreadable values left alone
- the tool never printing values

A local PostgreSQL 16 check with 250 synthetic lab rows is recorded in `implementation-status.md`.

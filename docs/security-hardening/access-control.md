# Staff access to patient records

## Before this change

`assert_patient_access` let **any** verified clinician or admin open **any** patient's profile, reports, lab tracker and care plans. `/clinical-review/queue` listed every patient's pending care plan to every clinician and admin. This was assessment finding M4.

## Now (`CAREWISE_STAFF_ACCESS_MODE=grants`, the default)

| Who | Can see a patient's records when… |
|---|---|
| The patient | It is their own profile |
| A clinician | The patient added that clinician's verified, listed account to their care team, and the grant is not expired or revoked |
| An admin | Never through the admin role. Admins keep `/admin/summary`, which returns counts only. |
| Another patient | Never |

**Care team API.** Only the profile owner can use these endpoints. Anyone else gets 404, so a clinician cannot grant themselves access.

| Endpoint | Purpose |
|---|---|
| `POST /patients/{id}/care-team {clinician_email, days?}` | Add a clinician. `days` is 1–365; leave it empty for no expiry. Only a verified account listed as a clinician in `CAREWISE_STAFF_EMAILS` can be added. The error message does not say which check failed, so the list cannot be probed. |
| `GET /patients/{id}/care-team` | Who has access, when it expires, and when it was revoked |
| `DELETE /patients/{id}/care-team/{grant_id}` | Revoke. The next request is refused, even with the same sign-in token. |

**Review queue.** A clinician sees only granted patients; admins see none. Reviewing a care plan checks the same grant.

**Audit.** `care_team_added` (with the number of days) and `care_team_removed` are recorded. Neither contains health content.

**Not in this change:** a break-glass emergency override. None was added, and none should be added without a separate, reviewed and logged design.

## Staged rollout

1. Before merging, check whether any staff currently rely on global access. `CAREWISE_STAFF_EMAILS` in Render lists them.
2. If they do, set `CAREWISE_STAFF_ACCESS_MODE=legacy_global` in Render, deploy, and have patients add their clinicians.
3. Then remove the variable to return to `grants`.

**Rollback:** set `legacy_global`. No data changes are needed. Migration 0024 only adds the table.

## Tests

`tests/api/test_care_access.py` has 10 tests:
- patient A cannot read patient B
- unassigned clinicians and admins are refused
- a granted clinician can read, and is refused immediately after revocation
- an expired grant is refused
- only the patient manages the care team: a clinician or another patient gets 404
- only verified, listed clinicians can be added, with a uniform message
- the queue lists only granted patients
- reviewing an unassigned plan is refused
- legacy mode restores global access
- forged and injected ids give a plain 404

`test_staff_roles.py` was updated: a verified clinician now needs a grant.

**Migration 0024:** upgrade, downgrade and upgrade pass on SQLite and on PostgreSQL 16 (local, synthetic).

**Website:** the patient-facing "Care team" controls are not built yet. Until then, grants are made through the API. That is the next frontend task, alongside the Your Data page.

## Account access review (20 Nov 2026)

A code review of every route, run on synthetic data. Nothing in production was changed.

- **Every route that returns or changes someone's records requires sign-in.** The routes open without
  sign-in are: sign-in and sign-up, password reset, the public catalogue and plan lists, health checks,
  the help chat, anonymous product signals, and links that carry their own secret token (doctor share
  links, clinic packet links, inbound email, reminder voice calls, the Stripe webhook). The founder
  summary needs the founder token. Cron routes need the cron token.
- **Every route that takes a patient, report or sign-in id checks it belongs to the person asking** (or
  to a patient who granted that clinician access). `tests/api/test_cross_account_sweep.py` now tries all
  of them, including the older `/upload-report`, `/analyze-report` and `/report-results`, as a second
  person. Each one is refused and leaks nothing. A missing or forged token gets 401.
- **New finding:** at startup, production rejected a placeholder sign-in signing key, but not a short one.
  Sign-in tokens are signed with HS256, and a key shorter than 32 bytes can be guessed offline from a
  single token. Startup now logs `security: CAREWISE_JWT_SECRET is shorter than 32 bytes` (the name only,
  never the value or its length). It is a warning, not a refusal to start, because nobody has checked
  the live key yet.

**Owner check.** After this deploys, search the `carewise-api` logs for `security:`. If the warning
appears, replace `CAREWISE_JWT_SECRET` in Render with a new random value of at least 48 characters. When
you do, everyone is signed out once.

**Not covered by this review:** the database network setting and the encryption backfill (see
`docs/runbooks/database-network-restriction.md` and `encryption-migration.md`), and penetration testing
by an independent tester.

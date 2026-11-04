# Render database network lockdown

**Status: BLOCKED on an owner action.** This session can only read Render settings, so the change below must be made by the owner in the dashboard.

## Current state (read 2026-11-02 through the Render API; no values or secrets read)

| Resource | Facts |
|---|---|
| `carewise-postgres` (`dpg-dasqa88473hc739g5bg0-a`) | PostgreSQL 18, Oregon, plan `0.1c-256mb`, 1 GB disk, no high availability, no read replicas. **`ipAllowList: 0.0.0.0/0 ("everywhere")`**: the database accepts connections from any internet address, and the password plus TLS are the only barrier. |
| `carewise-api` (`srv-d8o6fcreo5us73drv1v0`) | Docker web service, Oregon (same region as the database), free plan. `render.yaml` sets `CAREWISE_DATABASE_URL` from `fromDatabase … connectionString`, which is Render's **internal** connection string. |
| `carewise-frontend` | Static site, no database access |
| Other database users | None found. CI uses SQLite (`backend-ci.yml`). The reminder cron calls the API over HTTPS (`/reminders/dispatch` with a token) and never touches the database. No GitHub workflow holds a database URL. |

## Required network paths

| Path | Needs public access? |
|---|---|
| carewise-api → database | No: the internal URL, same region |
| Migrations | No: run by the API at startup (`init_local_database` → `alembic upgrade`) |
| `scripts/security/encrypt_fields.py` (backfill or rotation) | No: run in a Render Shell on `carewise-api`, which uses the internal URL |
| Render backups and point-in-time recovery | No: managed by Render, unaffected by the allow list |
| Owner ad-hoc access (psql or a GUI from a laptop) | Only if wanted, and then for the owner's own IP for a limited time |

## Safe target configuration

`ipAllowList` should be **empty** (no external access). If the owner needs occasional laptop access, list only their current IP as a `/32` and remove it afterwards.

## Before the change: verify the replacement path

1. **Check the API uses the internal URL.** Dashboard → carewise-api → Environment → `CAREWISE_DATABASE_URL`, and look only at the host part.
   - The internal host looks like `dpg-dasqa88473hc739g5bg0-a` (no domain).
   - The external host ends in `.oregon-postgres.render.com`. If it does, replace the value with the database's **Internal Database URL** (Dashboard → carewise-postgres → Connect → Internal) and redeploy.
   - Do not copy the URL anywhere else.
2. **Check the API is healthy:** `curl -s https://carewise-api.onrender.com/ready` should report the database as ready.

## The change (owner, in the dashboard)

1. Dashboard → carewise-postgres → **Networking** → Access Control.
2. Delete the `0.0.0.0/0 everywhere` rule. If you want laptop access, add your IP as `/32` instead.
3. Save.

## Verify afterwards

- `curl -s https://carewise-api.onrender.com/ready` shows the database ready.
- The GitHub "Live Backend Smoke" workflow passes on its next run, or run it manually.
- Sign in on the website and open the report history (synthetic account).
- From a machine that is not on the allow list, `psql "<external URL>"` must be refused. The owner runs this, because only they hold the URL.

## Rollback

If the API cannot reach the database after the change, add `0.0.0.0/0` back under Networking. That restores the previous state at once. Then fix step 1 (internal URL) and repeat.

## Monitoring

- The weekly drift check should read `ipAllowList` through the Render API and alert if it is not empty or not owner `/32` entries only (planned in `implementation-status.md`, workstream 8).
- Separately from networking: the database runs with high availability off and disk autoscaling off on a 1 GB disk (assessment L2). That is a capacity risk, not an access risk.

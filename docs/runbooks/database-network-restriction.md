# Runbook: remove public access to the production database

Finding H2 in `SECURITY-REVIEW.md`: `carewise-postgres` accepts connections from any address
(`0.0.0.0/0`). This change is in production security settings, so it's done by the owner in the Render
dashboard. The connection tools used so far can read this setting but can't change it.

**Clean logs alone are not proof.** Do every check below before removing anything, and do the
rehearsal so the undo step has been tried for real.

## Evidence gathered so far (2026-10-23)

| Check | Result | What it proves | Still needed |
|---|---|---|---|
| `render.yaml` sets `CAREWISE_DATABASE_URL` with `fromDatabase … property: connectionString` | Yes | The blueprint uses Render's **internal** connection string | Confirm the live value wasn't overridden by hand (step 1) |
| Database logs from 2026-10-21 to 2026-10-23: client addresses | Only private `10.x` addresses | The API reaches the database over Render's private network | Confirm nothing else (reports, a laptop, a backup tool) connects from outside (step 2) |
| Database logs for public client addresses in the same window | None found | No outside connections in those two days | Weekly or monthly jobs may not show up in two days (step 2) |

## Steps

1. **Check the live connection string.** Render → `carewise-api` → Environment → reveal
   `CAREWISE_DATABASE_URL`. The host after `@` must look like `dpg-…-a` with **nothing** after it. If it
   ends in `.oregon-postgres.render.com`, it's the external address: replace it with the database's
   **Internal Database URL**, save, wait for the redeploy, and check `/ready` before continuing. Don't
   paste the value anywhere.
2. **List anything else that uses the database from outside Render:** a SQL client on a laptop, a
   reporting tool, backup scripts or GitHub Actions. None are known in this project (no workflow
   connects to the database). If one exists, add its fixed IP as a `/32` rule before step 5.
3. **Confirm you can recover data.** Render → `carewise-postgres` → Recovery: note the latest backup
   or the point-in-time recovery window available on this plan.
4. **Rehearse the undo, with no effect on traffic.** In `carewise-postgres` → Networking → Access
   Control, add the documentation-only address `203.0.113.1/32` with description `rehearsal`, save,
   confirm it appears, then delete it and save. This proves you can edit the list and that changes apply.
5. **Make the change.** Delete the `0.0.0.0/0` ("everywhere") rule and save. Note the time.
6. **Verify within 5 minutes:**
   - `https://carewise-api.onrender.com/ready` shows `"database":true`.
   - GitHub → carewise-frontend → Actions → **Production monitor** → Run workflow: all steps green.
   - GitHub → carewise-production-backend → Actions → **Deploy smoke** → Run workflow: green.
   - Render → `carewise-api` → Logs: no new database connection errors.
7. **Undo if anything fails:** Networking → add `0.0.0.0/0`, description `everywhere`, save. This is the
   same edit you rehearsed in step 4. Re-run the checks in step 6, then investigate before trying again.

## After it's done

Update H2 in `carewise-frontend/docs/SECURITY-REVIEW.md` to closed, with the date and the check results.

# CareWise Investor Demo Runbook

Live demo URLs:

- Website: https://carewise-frontend.onrender.com
- API: https://carewise-api.onrender.com

Use synthetic data only. Never type real patient information during a demo.

## If the live API is down

`/health` does not touch the database, so if it never answers, the API
process is not starting. The Docker command runs `python -m app.db.migrate`
before `uvicorn`, so an unreachable database stops the whole service.

1. Render dashboard → `carewise-api` → Logs. Look for a database connection
   error during `app.db.migrate`.
2. Render dashboard → `carewise-postgres`. Render's free Postgres expires 30
   days after creation. If it expired, create a new database (a paid plan
   does not expire) and copy its Internal Database URL.
3. `carewise-api` → Environment → set `CAREWISE_DATABASE_URL` to the new URL.
   The deploy runs migrations and creates the tables.
4. Confirm with the `Live Backend Smoke` GitHub workflow (Actions tab →
   Run workflow), or locally:
   `python3 scripts/smoke_test_deploy.py --base-url https://carewise-api.onrender.com`

A new database starts empty, so create a fresh demo account afterwards.

## Before the meeting

- Free Render services sleep after 15 idle minutes and take about a minute
  to wake. The `Keep API Warm` workflow pings `/health` every 10 minutes
  once it is on `main`. For a guaranteed-fast demo, move `carewise-api` to a
  paid instance type, which never sleeps.
- 10 minutes before: open the website and wait for the home page to show
  API Online, Database Ready, Storage Ready.
- Create the demo account in advance (for example `demo@yourdomain.com`)
  so you log in instead of signing up on stage.

## Demo path (about 5 minutes)

1. Home: explain the promise, plain-English report explanations, and point
   at the live readiness badges.
2. Profile: log in with the prepared demo account.
3. Upload: press "Try sample report", then "Analyze report". Walk through the
   health score, detected values, key findings, and doctor questions.
4. Press "Save to trends", then History: show the saved report and trends.
5. Close on safety: CareWise is educational and not a diagnosis tool. Point
   to the disclaimer and the data deletion controls.

The sample-report analysis also runs in the browser, so step 3 still works
if the API is slow; sign-in and history need the API.

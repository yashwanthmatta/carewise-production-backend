# CareWise Investor Demo Runbook

Live demo URLs:

- Website: https://carewise-frontend.onrender.com
- API: https://carewise-api.onrender.com

Use synthetic data only. Never type real patient information during a demo.

## If the live API is down

The API now starts even when the database or a secret is missing, so
first open https://carewise-api.onrender.com/ready. Its `issues` list says
what is wrong (for example "Database unreachable" or the names of missing
settings). If even `/health` never answers, the service itself is not
running: check its Logs and that it is not suspended.

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
3. Upload: type "Mom" in "Whose report is this?", press "Try sample report",
   then "Analyze report". Walk through the health score, detected values, key
   findings, and doctor questions. Optional: drop in a text-based lab PDF
   (synthetic data only) to show it is read on the device.
4. Press "Doctor brief": show the one-page summary the patient can print
   or save as a PDF for their clinician.
5. Switch the language picker to Español: the same explanation in Spanish.
   Mention that translations are drafts pending clinician and medical
   translator review.
6. Press "Save to trends", then History: show the saved report, and filter
   "Show reports for" by Mom to show caregiver mode.
7. Close on safety: CareWise is educational and not a diagnosis tool. Point
   to the disclaimer and the data deletion controls.

The sample-report analysis, PDF reading, doctor brief, Spanish view and
caregiver history run in the browser, so they still work if the API is
slow; sign-in and cloud sync need the API. On a phone, the CareWise app's
Reports tab shows the same explanation offline ("Explain on this phone").

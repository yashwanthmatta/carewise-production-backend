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

Open https://carewise-frontend.onrender.com/#tour, or press "See a 1-minute
demo" on the home page. The guided demo runs entirely in the browser, so it
works even if the API or database is down. Press Next (or the right arrow,
or a presentation clicker); Esc exits. It follows a made-up patient, Maria,
and saves nothing.

1. The report: score 66/100, six key values and what to watch.
2. Every result against her lab's own range (kidney, liver, thyroid, blood
   count, vitamin D). Say: normal ranges differ by lab, so we use the lab's.
3. The 4-week plan: every tip says why ("Your LDL is 148 mg/dL") and where it
   comes from (American Heart Association, American Diabetes Association,
   CDC). It knows penicillin and lisinopril did not suit her. Say: it never
   names medicines or doses.
4. Spanish, one tap (drafts pending clinician and medical translator review).
5. The doctor brief, one printable page, including her history.
6. Her 20-year health record: conditions, medicines, what did not suit her.
7. A CT chest report explained: the radiologist's words, the follow-up line
   flagged as a question for the doctor, never the images.
8. "Now try it with your own report." Close on safety and proof:
   educational, not a diagnosis; tested on 1,000 lab PDFs, 27,000 blood-test
   results and 616 scan reports.

If there is time after the tour, show sign-in with the demo account (only
when the home page shows Database Ready).

The guided demo, sample-report analysis, PDF reading, doctor brief, Spanish
view and caregiver history run in the browser, so they still work if the API is
slow; sign-in and cloud sync need the API. On a phone, the CareWise app's
Reports tab shows the same explanation offline ("Explain on this phone").

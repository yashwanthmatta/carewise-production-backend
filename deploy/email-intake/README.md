# DocBridge email intake (Cloudflare Email Routing)

A clinic team member forwards a de-identified lab PDF to the clinic's private address,
`labs+CODE@in.<your domain>` (shown on the DocBridge screen). Cloudflare receives it,
`cloudflare-email-worker.js` posts the raw message to `POST /inbound/email/{token}`, and
the API stores each PDF encrypted under the clinic and adds a "New from email" lab to the
clinic inbox. The clinician opens it and the same lab reader used for uploads drafts it.

Pilot rules enforced by the API: the sender must be a member of that clinic, the subject
must contain `DEID`, at most 5 PDFs of 10 MB each. Anything else is dropped unstored.

## Setup

1. Make a long random token yourself (for example `openssl rand -hex 32`).
2. Render, API service, Environment:
   - `CAREWISE_INBOUND_EMAIL_DOMAIN` = `in.<your domain>`
   - `CAREWISE_INBOUND_EMAIL_TOKEN` = the token
3. Cloudflare, your domain, Email, Email Routing: enable it for the subdomain `in`
   (Settings, Subdomains). Cloudflare adds the MX records for `in.<your domain>` only, so
   mail for the main domain (Google Workspace) is untouched.
4. Workers & Pages, Create, "Hello World" Worker, paste `cloudflare-email-worker.js`,
   Deploy. Settings, Variables and Secrets, add secret `INTAKE_URL` =
   `https://<api host>/inbound/email/<token>`.
5. Email Routing, Routing rules, Catch-all for `in.<your domain>`: action "Send to a
   Worker", pick the Worker.
6. Test: from the email address of a clinic member, send a sample lab PDF to the clinic
   address with a subject like `DEID REF-101`. It appears in the clinic inbox within a
   minute (the first request can be slower while a free server wakes up).

Use only sample or de-identified labs until BAAs are signed. Cloudflare Email Routing is
fine for the pilot; switch to a provider that signs a BAA (for example Amazon SES, which
the endpoint also accepts via SNS) before real patient data.

## Scheduled jobs (reminder calls and nightly cleanup)

The same Worker runs the scheduled jobs, because GitHub's scheduled workflows only ran
every 2 to 6 hours in practice. A reminder is created only when its time falls in the
last 15 minutes, so a slow schedule silently skips most reminders.

1. Paste the current `cloudflare-email-worker.js` into the Worker and Deploy.
2. Settings, Variables and Secrets: add secret `CRON_TOKEN` = the same value as
   `CAREWISE_REMINDER_CRON_TOKEN` on the Render API service.
3. Settings, Triggers, Cron Triggers: add `*/5 * * * *` and `17 7 * * *`.
4. Check: Worker, Logs, a run every 5 minutes with no "returned" error lines.

The GitHub workflow `scheduled-jobs.yml` stays as a backup; running the dispatch twice is
safe (each reminder time is recorded once and calls count their attempts).

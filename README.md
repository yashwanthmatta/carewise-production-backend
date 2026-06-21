# CareWise Production Backend

This is the production-oriented backend for CareWise.

It is separate from the local standard-library prototype in `outputs/carewise-backend/`.

## What This Adds

- FastAPI application structure
- PostgreSQL-ready SQLAlchemy models
- Authentication and role-based access control
- Consent history model and routes
- Encrypted health-field helper
- Clinical review workflow
- Background queue interface
- OpenTelemetry instrumentation hooks
- Docker and Docker Compose
- Alembic database migrations
- Production Docker startup command
- Deployment smoke-test script
- Multipart report file upload with file-size/type controls
- Patient ownership checks on protected patient records
- Privacy export, deletion request, and account deletion endpoints
- Security headers middleware
- GitHub Actions backend CI
- Secret generation helper
- k6 and Locust load-test plans
- Security/privacy review checklist
- Scale guardrail checklist
- Cloud deployment notes

## Important

This backend can run locally with Docker and can be uploaded to a cloud host.
It is still not cleared for real patient use until healthcare legal, privacy, security,
and clinical review are complete.

## Local Development

Install dependencies in a virtual environment:

```bash
pip install -e ".[dev]"
```

Start with Docker:

```bash
env PATH=/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin /Applications/Docker.app/Contents/Resources/bin/docker compose up --build
```

Run tests/checks:

```bash
python3 -m pytest
python3 -m ruff check .
python3 tests/static_readiness_check.py
```

Check file storage configuration:

```bash
python3 scripts/check_storage.py
```

Generate production secrets:

```bash
python3 scripts/generate_secrets.py
```

Smoke-test a deployed backend:

```bash
python3 scripts/smoke_test_deploy.py --base-url https://YOUR-API-URL
```

The smoke test verifies `/health`, `/features`, `/ready`, auth, consent,
profile sync, text report analysis, saved analysis history, multipart file
upload, protected report download URL creation, recommendations, doctor search,
insurance matching, subscription checkout, notification registration, privacy
export, and smoke-account cleanup. Use `--keep-data` only when debugging a
failed deploy because it leaves the smoke-test account and reports in the
target environment.

## Main Commands

Run API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run worker:

```bash
python -m app.workers.worker
```

Run k6:

```bash
k6 run load-tests/k6-carewise.js
```

Run Locust:

```bash
locust -f load-tests/locustfile.py
```

## Upload Path

Recommended first upload: Render.

Read:

```text
deploy/cloud_deployment.md
deploy/render/render.yaml
render.yaml
```

Required cloud services:

- Web service for API
- Managed PostgreSQL
- Durable private object storage for report files, such as Cloudflare R2 or AWS S3
- Secret manager or dashboard environment variables
- HTTPS

Redis and the worker are included for later scale work, but the first Render Blueprint deploys only the API and Postgres to avoid paid background services.

The container automatically runs:

```bash
python -m app.db.migrate
```

before starting the API.

## Report Storage

The backend now supports:

- JSON report uploads for pasted/OCR text at `POST /reports/upload`
- Multipart file uploads at `POST /reports/upload-file`
- Protected file access through `GET /reports/{report_id}/download`
- Saved report explanation history through `GET /reports/{report_id}/analyses`
- Content-type allow-listing
- File-size limits through `CAREWISE_MAX_REPORT_FILE_BYTES`
- Local object-store style paths under `CAREWISE_LOCAL_STORAGE_DIR`
- Optional S3-compatible storage through `CAREWISE_STORAGE_BACKEND=s3`
- Automatic text extraction for `.txt` uploads and text-based PDFs
- Optional OpenAI vision OCR for report images when `CAREWISE_OPENAI_API_KEY` is set
- Encrypted report text stored in PostgreSQL
- File metadata stored in PostgreSQL

Original file downloads are access-controlled by patient ownership and return a
short-lived URL. Do not expose private bucket paths directly in frontend code.

For local development this writes files to `storage/`. The production Render
Blueprint now expects S3-compatible durable storage. For CareWise, use
Cloudflare R2 first if you want S3-compatible storage with a generous free tier,
or AWS S3 when you are ready for a HIPAA-aligned AWS architecture.

S3/R2/GCS-compatible configuration:

```text
CAREWISE_STORAGE_BACKEND=s3
CAREWISE_S3_BUCKET=your-private-bucket
CAREWISE_S3_REGION=us-east-1
CAREWISE_S3_ENDPOINT_URL= # optional, use for Cloudflare R2 or compatible providers
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

After deploy, `/features` should show `"durable_storage": true` and
`"storage_ready": true`. `/ready` should return status `ready`.

Optional OCR configuration:

```text
CAREWISE_OPENAI_API_KEY=...
CAREWISE_OPENAI_OCR_MODEL=gpt-5.5
```

Without an OCR key, images and scanned PDFs are still stored privately, but
analysis will ask the user to paste OCR text or key lab values before relying on
report interpretation.

## Subscription Checkout

The backend exposes subscription plan metadata at `GET /subscriptions/plans`.
`POST /subscriptions/checkout` creates a manual checkout record by default. When
`CAREWISE_STRIPE_SECRET_KEY` is configured, the same endpoint creates a Stripe
Checkout Session in subscription mode and returns Stripe's hosted checkout URL.

Stripe configuration:

```text
CAREWISE_STRIPE_SECRET_KEY=sk_test_or_live_value
CAREWISE_STRIPE_SUCCESS_URL=https://your-frontend-domain.com/?checkout=success
CAREWISE_STRIPE_CANCEL_URL=https://your-frontend-domain.com/?checkout=cancelled
```

Only plan, price, subscription reference, and account email are sent to Stripe.
Health report, symptom, medication, and care-plan details must stay inside the
CareWise backend.

Setup guides:

- `deploy/storage/cloudflare-r2.md`
- `deploy/storage/aws-s3.md`

## Privacy Endpoints

- `GET /privacy/me/export` returns the signed-in user's account, patient, consent,
  report metadata, care plan metadata, subscriptions, notifications, and audit metadata.
- `POST /privacy/me/delete-request` records a deletion request for app-store and
  support workflows.
- `DELETE /privacy/me` deletes the signed-in user's account-linked records.

Do not enable real patient use until legal counsel validates retention rules,
backup deletion behavior, audit retention, and regional privacy requirements.

## Production Warning

Before real patient use, this still needs:

- Healthcare legal review
- HIPAA/privacy analysis
- Security review
- Clinician review of medical logic
- Real secret management
- Cloud deployment hardening
- CI/CD
- Pen testing
- Backup/restore drills

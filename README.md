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
```

Required cloud services:

- Web service for API
- Managed PostgreSQL
- Durable object storage for real report files before real patient use
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
- Content-type allow-listing
- File-size limits through `CAREWISE_MAX_REPORT_FILE_BYTES`
- Local object-store style paths under `CAREWISE_LOCAL_STORAGE_DIR`
- Optional S3-compatible storage through `CAREWISE_STORAGE_BACKEND=s3`
- Encrypted report text stored in PostgreSQL
- File metadata stored in PostgreSQL

For local development this writes files to `storage/`. On Render free hosting,
`/tmp/carewise-storage` is useful for testing but is not durable. Before real
patient uploads, connect durable private object storage such as AWS S3,
Cloudflare R2, or Google Cloud Storage and sign file access through the backend.

S3/R2/GCS-compatible configuration:

```text
CAREWISE_STORAGE_BACKEND=s3
CAREWISE_S3_BUCKET=your-private-bucket
CAREWISE_S3_REGION=us-east-1
CAREWISE_S3_ENDPOINT_URL= # optional, use for Cloudflare R2 or compatible providers
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

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

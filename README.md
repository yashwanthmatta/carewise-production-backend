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
python3 tests/static_readiness_check.py
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
- Worker service
- Managed PostgreSQL
- Managed Redis
- Secret manager or dashboard environment variables
- HTTPS

The container automatically runs:

```bash
python -m app.db.migrate
```

before starting the API.

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

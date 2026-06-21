# Cloud Deployment Plan

## Best First Upload Choice

Use Render first. It is the simplest path for a beginner.

For the first free prototype deploy, run:

- One Docker web service for the API.
- Managed PostgreSQL.
- HTTPS automatically.
- Environment variables from a dashboard.

Add Redis and the background worker later when you are ready to pay for always-on background work.

Fly.io, AWS, and GCP files are included, but Render is the recommended first official upload.

## Before Upload

From `outputs/carewise-production-backend/`, generate production secrets:

```bash
python3 scripts/generate_secrets.py
```

Save the two printed values somewhere private:

- `CAREWISE_JWT_SECRET`
- `CAREWISE_FIELD_ENCRYPTION_KEY`

Never commit real production secrets into GitHub.

## Required Production Environment Variables

- `CAREWISE_ENV=production`
- `CAREWISE_DATABASE_URL`
- `CAREWISE_JWT_SECRET`
- `CAREWISE_FIELD_ENCRYPTION_KEY`
- `CAREWISE_ALLOWED_ORIGINS`
- `CAREWISE_OTEL_EXPORTER_OTLP_ENDPOINT`

For the first upload, `CAREWISE_ALLOWED_ORIGINS` should be the frontend URL only, for example:

```text
https://carewise-web.onrender.com
```

For local testing, keep:

```text
http://localhost:4173,http://localhost:3000
```

## Render Upload Steps

1. Push this backend folder to GitHub.
2. In Render, create a Blueprint from root `render.yaml`, or use `deploy/render/render.yaml` if you prefer a nested Blueprint path.
3. Create managed PostgreSQL.
4. Set `CAREWISE_JWT_SECRET` and `CAREWISE_FIELD_ENCRYPTION_KEY` from `scripts/generate_secrets.py`.
5. Set `CAREWISE_ALLOWED_ORIGINS` to the deployed frontend URL.
6. Set durable storage variables:

```text
CAREWISE_STORAGE_BACKEND=s3
CAREWISE_S3_BUCKET=carewise-private-reports
CAREWISE_S3_REGION=us-east-1
CAREWISE_S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
AWS_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
```

For AWS S3, leave `CAREWISE_S3_ENDPOINT_URL` blank and use AWS credentials
scoped to the private bucket.

7. Deploy the API service.
8. Open `/health`, `/features`, and `/ready` on the API URL.
9. Run:

```bash
python3 scripts/smoke_test_deploy.py --base-url https://YOUR-API-URL
```

The smoke test signs up a test patient, records consent, creates a profile,
generates a care plan, analyzes report text, uploads a report file, verifies
protected report download access, and checks the main marketplace/mobile APIs.

## Database Migrations

The Docker container runs this before API startup:

```bash
python -m app.db.migrate
```

This creates the first production schema from:

```text
migrations/versions/0001_initial_schema.py
```

## Frontend Connection

After backend upload, update the frontend API URL field to the deployed API URL:

```text
https://YOUR-API-URL
```

Then test:

1. Create account.
2. Record consent.
3. Sync profile.
4. Generate care plan.
5. Sync latest plan.
6. Load consent history.

## First Production Environment

Use one cloud region first:

- API service in containers.
- Managed PostgreSQL.
- Managed Redis.
- Object storage.
- Secret manager.
- Load balancer.
- HTTPS certificate.
- Managed logs and metrics.

## Deployment Pipeline

1. Run tests.
2. Run lint/static checks.
3. Build container.
4. Scan container.
5. Deploy to staging.
6. Run smoke tests.
7. Promote to production.
8. Monitor error rate and latency.

## Required Environment Variables

- `CAREWISE_DATABASE_URL`
- `CAREWISE_REDIS_URL`
- `CAREWISE_JWT_SECRET`
- `CAREWISE_FIELD_ENCRYPTION_KEY`
- `CAREWISE_ALLOWED_ORIGINS`
- `CAREWISE_OTEL_EXPORTER_OTLP_ENDPOINT`

## Production Runtime

- Minimum 2 API replicas.
- Horizontal autoscaling.
- Separate worker deployment.
- Database backups.
- Redis persistence only if needed.
- OpenTelemetry collector.

## Later Regional Scaling

Add regions only after product-market fit and operational maturity.

Regional rollout requires:

- Data residency review.
- Regional database.
- Regional queues.
- Regional object storage.
- Regional incident response.
- Regional clinical review coverage.

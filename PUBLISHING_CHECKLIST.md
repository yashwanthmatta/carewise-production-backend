# CareWise Publishing Checklist

This checklist is the current path from MVP to Android/iOS submission.

## Backend

- Deploy `carewise-production-backend` from root `render.yaml`.
- Configure Render Postgres.
- Configure durable private object storage:
  - Cloudflare R2 or AWS S3.
  - `CAREWISE_STORAGE_BACKEND=s3`.
  - Private bucket only, no public access.
  - Bucket-scoped access key only.
- Set secrets:
  - `CAREWISE_JWT_SECRET`.
  - `CAREWISE_FIELD_ENCRYPTION_KEY`.
  - `CAREWISE_ALLOWED_ORIGINS`.
  - `AWS_ACCESS_KEY_ID`.
  - `AWS_SECRET_ACCESS_KEY`.
- Confirm:
  - `GET /health` returns `ok`.
  - `GET /features` shows `durable_storage: true`.
  - `GET /ready` returns `ready`.
  - `python3 scripts/smoke_test_deploy.py --base-url https://YOUR-API-URL` passes, including multipart file upload and protected download.

## Web Frontend

- Deploy the web app.
- Set backend API URL to the deployed API.
- Test:
  - Signup/login.
  - Report text analysis.
  - Secure report upload when signed in.
  - Protected report download/open flow.
  - History.
  - Profile.

## Mobile App

- Use `outputs/carewise-mobile-app`.
- Configure `extra.apiBaseUrl` in `app.json`.
- Build with EAS:
  - `npx eas build --platform android --profile preview`.
  - `npx eas build --platform ios --profile preview`.
- Test on real iPhone and Android before store submission.

## Apple App Store

- Apple Developer account required.
- App Privacy details required.
- Medical disclaimer required.
- Data deletion path required.
- Do not claim diagnosis, cure, prevention, or treatment.
- Add reviewer notes explaining CareWise is educational report explanation.

## Google Play

- Google Play Console account required.
- Data Safety form required.
- Health app declarations may be required.
- Privacy policy URL required.
- Data deletion URL required.

## Before Real Patient Data

- Healthcare attorney/privacy review.
- Security review.
- Clinician review of report explanations.
- Incident response plan.
- Backup/restore test.
- Penetration test.
- Audit log retention policy.
- HIPAA/BAA review for every vendor.

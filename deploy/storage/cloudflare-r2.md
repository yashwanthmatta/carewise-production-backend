# Cloudflare R2 Storage Setup

CareWise can use Cloudflare R2 through its S3-compatible API.

## Create R2 Bucket

1. Open Cloudflare Dashboard.
2. Go to R2 Object Storage.
3. Create a private bucket, for example `carewise-private-reports`.
4. Do not enable public bucket access for patient files.

Cloudflare's S3-compatible endpoint format is:

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

Cloudflare R2 uses S3 region `auto`; for SDK compatibility, `us-east-1` also aliases to `auto`.

## Create R2 Token

Create an R2 API token with access only to the CareWise private bucket.

Use least privilege:

- Object read
- Object write
- Object delete

Do not use a broad account token in production.

## Render Environment Variables

Set these on the `carewise-api` Render service:

```text
CAREWISE_STORAGE_BACKEND=s3
CAREWISE_S3_BUCKET=carewise-private-reports
CAREWISE_S3_REGION=us-east-1
CAREWISE_S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
AWS_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
```

Keep these secret. Do not paste them into frontend code, GitHub, Slack, screenshots, or public docs.

## Verify

After setting the variables and redeploying Render:

```bash
python3 scripts/check_storage.py
```

Expected:

```json
{
  "status": "passed",
  "storage_backend": "s3",
  "deleted": true
}
```

## Notes

- Report text is encrypted in PostgreSQL.
- Original report files are private objects in R2.
- The backend stores only the storage key and private storage URL.
- Account deletion now attempts to delete stored report objects before deleting database rows.

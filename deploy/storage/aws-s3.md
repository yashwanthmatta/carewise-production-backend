# AWS S3 Storage Setup

CareWise can use a private AWS S3 bucket for durable report file storage.

## Create Bucket

1. Create a private S3 bucket, for example `carewise-private-reports`.
2. Keep Block Public Access enabled.
3. Enable default server-side encryption.
4. Prefer a dedicated AWS IAM user or role for CareWise.

## IAM Permissions

The backend needs object-level permissions for one bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::carewise-private-reports/*"
    }
  ]
}
```

## Render Environment Variables

```text
CAREWISE_STORAGE_BACKEND=s3
CAREWISE_S3_BUCKET=carewise-private-reports
CAREWISE_S3_REGION=us-east-1
CAREWISE_S3_ENDPOINT_URL=
AWS_ACCESS_KEY_ID=<AWS_ACCESS_KEY_ID>
AWS_SECRET_ACCESS_KEY=<AWS_SECRET_ACCESS_KEY>
```

## Verify

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

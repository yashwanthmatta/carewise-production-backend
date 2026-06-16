import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfileobj

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    storage_url: str
    file_size_bytes: int


def safe_file_name(file_name: str) -> str:
    cleaned = SAFE_NAME_PATTERN.sub("-", Path(file_name or "report-upload").name).strip(".-")
    return cleaned[:160] or "report-upload"


def storage_root() -> Path:
    root = Path(settings.local_storage_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


async def store_report_file(patient_id: str, report_id: str, file: UploadFile) -> StoredFile:
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in settings.allowed_report_content_type_list:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported report file type.",
        )

    file_name = safe_file_name(file.filename or "report-upload")
    storage_key = f"reports/{patient_id}/{report_id}/{file_name}"
    temp_path = Path(tempfile.mkstemp(prefix="carewise-report-")[1])
    try:
        total = await write_upload_to_temp(file, temp_path)
        if settings.storage_backend.lower() == "s3":
            storage_url = upload_temp_file_to_s3(temp_path, storage_key, content_type)
        else:
            storage_url = persist_temp_file_locally(temp_path, storage_key)
    finally:
        temp_path.unlink(missing_ok=True)

    return StoredFile(
        storage_key=storage_key,
        storage_url=storage_url,
        file_size_bytes=total,
    )


async def write_upload_to_temp(file: UploadFile, temp_path: Path) -> int:
    total = 0
    with temp_path.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > settings.max_report_file_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Report file is larger than the {settings.max_report_file_bytes} byte limit.",
                )
            output.write(chunk)
    return total


def persist_temp_file_locally(temp_path: Path, storage_key: str) -> str:
    target_path = storage_root() / storage_key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("rb") as source, target_path.open("wb") as target:
        copyfileobj(source, target)
    return f"local://{storage_key}"


def upload_temp_file_to_s3(temp_path: Path, storage_key: str, content_type: str) -> str:
    if not settings.s3_bucket:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3 storage is enabled but CAREWISE_S3_BUCKET is not configured.",
        )
    import boto3

    client_kwargs = {"region_name": settings.s3_region}
    if settings.s3_endpoint_url:
        client_kwargs["endpoint_url"] = settings.s3_endpoint_url
    client = boto3.client("s3", **client_kwargs)
    with temp_path.open("rb") as source:
        client.upload_fileobj(
            source,
            settings.s3_bucket,
            storage_key,
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )
    return f"s3://{settings.s3_bucket}/{storage_key}"

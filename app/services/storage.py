import re
from dataclasses import dataclass
from pathlib import Path

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
    target_path = storage_root() / storage_key
    target_path.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.max_report_file_bytes
    total = 0
    with target_path.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Report file is larger than the {max_bytes} byte limit.",
                )
            output.write(chunk)

    return StoredFile(
        storage_key=storage_key,
        storage_url=f"local://{storage_key}",
        file_size_bytes=total,
    )

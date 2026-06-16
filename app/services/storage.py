import base64
import json
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfileobj

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
PDF_CONTENT_TYPES = {"application/pdf"}
MAX_OCR_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    storage_url: str
    file_size_bytes: int
    extracted_text: str = ""


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
        extracted_text = extract_text_from_temp_file(temp_path, content_type, file_name)
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
        extracted_text=extracted_text,
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


def extract_text_from_temp_file(temp_path: Path, content_type: str, file_name: str) -> str:
    if content_type == "text/plain" or file_name.lower().endswith(".txt"):
        return decode_text_file(temp_path)

    if content_type in PDF_CONTENT_TYPES or file_name.lower().endswith(".pdf"):
        return extract_text_from_pdf(temp_path)

    if content_type in IMAGE_CONTENT_TYPES:
        return extract_text_with_openai_vision(temp_path, content_type)

    return ""


def decode_text_file(temp_path: Path) -> str:
    raw = temp_path.read_bytes()[:120_000]
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding).strip()[:12000]
        except UnicodeDecodeError:
            continue
    return ""


def extract_text_from_pdf(temp_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(temp_path))
        pages = []
        for page in reader.pages[:8]:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages).strip()[:12000]
    except Exception:
        return ""


def extract_text_with_openai_vision(temp_path: Path, content_type: str) -> str:
    api_key = settings.clean_env_value(settings.openai_api_key)
    if not api_key:
        return ""

    image_bytes = temp_path.read_bytes()
    if len(image_bytes) > MAX_OCR_BYTES:
        return ""

    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    payload = {
        "model": settings.openai_ocr_model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Extract readable text and lab values from this healthcare report image. "
                            "Return plain text only. Do not diagnose, infer conditions, or add advice."
                        ),
                    },
                    {"type": "input_image", "image_url": data_url, "detail": "high"},
                ],
            }
        ],
        "max_output_tokens": 1600,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return ""

    return response_text(result).strip()[:12000]


def response_text(result: dict) -> str:
    if isinstance(result.get("output_text"), str):
        return result["output_text"]

    chunks = []
    for output in result.get("output", []):
        for content in output.get("content", []):
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


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


def delete_stored_file(storage_key: str) -> bool:
    if not storage_key:
        return False
    if settings.storage_backend.lower() == "s3":
        if not settings.s3_bucket:
            return False
        import boto3

        client_kwargs = {"region_name": settings.s3_region}
        if settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3_endpoint_url
        client = boto3.client("s3", **client_kwargs)
        client.delete_object(Bucket=settings.s3_bucket, Key=storage_key)
        return True

    target_path = storage_root() / storage_key
    existed = target_path.exists()
    target_path.unlink(missing_ok=True)
    return existed

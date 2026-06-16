import json
import tempfile
import time
from pathlib import Path

from app.core.config import settings
from app.services.storage import delete_stored_file, persist_temp_file_locally, upload_temp_file_to_s3


def main() -> int:
    storage_key = f"storage-check/{int(time.time())}.txt"
    temp_path = Path(tempfile.mkstemp(prefix="carewise-storage-check-")[1])
    temp_path.write_text("CareWise storage check. No patient data.\n", encoding="utf-8")
    try:
        if settings.storage_backend.lower() == "s3":
            storage_url = upload_temp_file_to_s3(temp_path, storage_key, "text/plain")
        else:
            storage_url = persist_temp_file_locally(temp_path, storage_key)
        deleted = delete_stored_file(storage_key)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "storage_backend": settings.storage_backend,
                    "storage_url": storage_url,
                    "deleted": deleted,
                    "bucket": settings.s3_bucket if settings.storage_backend.lower() == "s3" else "",
                    "endpoint_configured": bool(settings.s3_endpoint_url),
                },
                indent=2,
            )
        )
        return 0
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())

"""Secrets carried in URLs never reach the request log (20 Nov 2026). Synthetic tokens only."""

import logging

from app.core import log_redaction
from app.main import create_app

TOKEN = "synthetic-secret-token-abc123"


def access_record(path: str) -> logging.LogRecord:
    # The same shape uvicorn's access logger uses: '%s - "%s %s HTTP/%s" %d'.
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', ("10.0.0.1:0", "POST", path, "1.1", 200), None)


def rendered(path: str) -> str:
    record = access_record(path)
    log_redaction.RedactSecretsInUrls().filter(record)
    return record.getMessage()


def test_path_and_query_secrets_are_redacted():
    for path in (
        f"/inbound/email/{TOKEN}",
        f"/reminders/voice/{TOKEN}",
        f"/reminders/voice/{TOKEN}/answer",
        f"/auth/oidc/google/callback?code={TOKEN}&state={TOKEN}",
        f"/somewhere?token={TOKEN}",
    ):
        line = rendered(path)
        assert TOKEN not in line, line
        assert "[redacted]" in line


def test_ordinary_lines_are_unchanged():
    assert rendered("/reports?patient_id=patient_1").endswith('"POST /reports?patient_id=patient_1 HTTP/1.1" 200')
    assert "/reminders/voice/[redacted]/answer" in rendered(f"/reminders/voice/{TOKEN}/answer")


def test_the_app_installs_the_filter_once():
    create_app()
    create_app()
    filters = [f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, log_redaction.RedactSecretsInUrls)]
    assert len(filters) == 1


def test_a_real_access_log_line_is_redacted(caplog):
    create_app()
    logger = logging.getLogger("uvicorn.access")
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        logger.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1:0", "POST", f"/inbound/email/{TOKEN}", "1.1", 404)
    assert TOKEN not in caplog.text and "/inbound/email/[redacted]" in caplog.text

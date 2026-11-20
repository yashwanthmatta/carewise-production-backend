"""Keep secrets that travel in URLs out of the request log.

Uvicorn's access log writes each request's full path. Some paths carry a secret: the inbound email
token (`/inbound/email/<token>`), reminder call tokens (`/reminders/voice/<token>`), and the one-time
`code` and `state` a sign-in provider returns to `/auth/oidc/<provider>/callback?code=…&state=…`.
Anyone who can read the logs could replay them. This filter replaces them with `[redacted]`
before the line is written; the rest of the line (method, route, status) stays for debugging.
"""

import logging
import re

_PATH_SECRETS = re.compile(r"(/inbound/email/|/reminders/voice/)[^/?#\s]+")
_QUERY_SECRETS = re.compile(r"([?&](?:code|state|token|id_token|access_token|refresh_token)=)[^&#\s]*", re.IGNORECASE)
REDACTED = "[redacted]"


def redact_url(text: str) -> str:
    text = _PATH_SECRETS.sub(lambda m: m.group(1) + REDACTED, text)
    return _QUERY_SECRETS.sub(lambda m: m.group(1) + REDACTED, text)


class RedactSecretsInUrls(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and record.args:
            record.args = tuple(redact_url(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = redact_url(record.msg)
        return True


def install() -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactSecretsInUrls) for f in logger.filters):
            logger.addFilter(RedactSecretsInUrls())

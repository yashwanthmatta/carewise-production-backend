SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # The API is only served over HTTPS; browsers should never try plain HTTP.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # Responses can contain health information: never keep them in a browser or proxy cache.
    "Cache-Control": "no-store",
}


def apply_security_headers(response) -> None:
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)

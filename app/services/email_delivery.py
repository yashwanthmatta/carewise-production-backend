from email.message import EmailMessage
import smtplib
import ssl
from urllib.parse import urlencode

from app.core.config import settings


def password_reset_url(token: str) -> str:
    frontend_url = settings.clean_env_value(settings.frontend_url).rstrip("/")
    return f"{frontend_url}/?{urlencode({'reset_token': token})}#account-title"


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    if not settings.email_delivery_enabled:
        raise RuntimeError("Email delivery is not configured.")

    reset_url = password_reset_url(reset_token)
    message = EmailMessage()
    message["Subject"] = "Reset your CareWise password"
    message["From"] = settings.clean_env_value(settings.smtp_from_email)
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "You requested a CareWise password reset.",
                "",
                f"Open this link to reset your password: {reset_url}",
                "",
                "This link expires soon. If you did not request it, you can ignore this email.",
            ]
        )
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.clean_env_value(settings.smtp_host), settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=context)
        smtp.login(settings.clean_env_value(settings.smtp_username), settings.clean_env_value(settings.smtp_password))
        smtp.send_message(message)

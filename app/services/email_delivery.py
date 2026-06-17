from email.message import EmailMessage
import smtplib
import ssl
from urllib.parse import urlencode

from app.core.config import settings


def password_reset_url(token: str) -> str:
    frontend_url = settings.clean_env_value(settings.frontend_url).rstrip("/")
    return f"{frontend_url}/?{urlencode({'reset_token': token})}#account-title"


def email_verification_url(token: str) -> str:
    frontend_url = settings.clean_env_value(settings.frontend_url).rstrip("/")
    return f"{frontend_url}/?{urlencode({'verify_token': token})}#account-title"


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    if not settings.email_delivery_enabled:
        raise RuntimeError("Email delivery is not configured.")

    reset_url = password_reset_url(reset_token)
    message = base_message(to_email, "Reset your CareWise password")
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

    send_email(message)


def send_email_verification(to_email: str, verification_token: str) -> None:
    if not settings.email_delivery_enabled:
        raise RuntimeError("Email delivery is not configured.")

    verify_url = email_verification_url(verification_token)
    message = base_message(to_email, "Verify your CareWise email")
    message.set_content(
        "\n".join(
            [
                "Welcome to CareWise.",
                "",
                f"Open this link to verify your email address: {verify_url}",
                "",
                "If you did not create a CareWise account, you can ignore this email.",
            ]
        )
    )
    send_email(message)


def base_message(to_email: str, subject: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.clean_env_value(settings.smtp_from_email)
    message["To"] = to_email
    return message


def send_email(message: EmailMessage) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP(settings.clean_env_value(settings.smtp_host), settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=context)
        smtp.login(settings.clean_env_value(settings.smtp_username), settings.clean_env_value(settings.smtp_password))
        smtp.send_message(message)

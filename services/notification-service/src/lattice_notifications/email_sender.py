"""Async SMTP helper (aiosmtplib).

In dev this targets MailHog (no auth, no TLS). Callers are expected to catch
exceptions — a failed email must never crash the consumer.
"""

from email.message import EmailMessage

import aiosmtplib

from lattice_notifications.config import get_settings

settings = get_settings()


async def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Raises on failure (caller decides what to do)."""
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        use_tls=settings.smtp_use_tls,
        # MailHog doesn't support STARTTLS; disabling avoids an auto-upgrade
        # attempt. When SMTP_USE_TLS is on we use implicit TLS via use_tls.
        start_tls=False,
    )

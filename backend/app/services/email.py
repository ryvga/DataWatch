"""SMTP-backed transactional email helpers."""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from app.config import settings

logger = logging.getLogger(__name__)


def _button(url: str, label: str) -> str:
    return (
        f'<a href="{escape(url)}" '
        'style="display:inline-block;background:#0f172a;color:#ffffff;'
        'padding:14px 22px;border-radius:8px;text-decoration:none;'
        'font-weight:700;margin:18px 0;">'
        f"{escape(label)}</a>"
    )


def _layout(title: str, body: str) -> str:
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#f6f8fb;font-family:Inter,Arial,sans-serif;color:#111827;">
    <div style="max-width:560px;margin:0 auto;padding:32px 18px;">
      <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;padding:28px;">
        <div style="font-size:14px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#2563eb;">Panopta</div>
        <h1 style="font-size:24px;line-height:1.25;margin:16px 0;color:#111827;">{escape(title)}</h1>
        <div style="font-size:16px;line-height:1.6;color:#374151;">{body}</div>
      </div>
      <p style="font-size:12px;line-height:1.5;color:#6b7280;margin:18px 4px;">
        You received this email because a Panopta account action was requested for this address.
      </p>
    </div>
  </body>
</html>
"""


def _send_email(to_email: str, subject: str, html: str) -> bool:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.FROM_EMAIL
    message["To"] = to_email
    message.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        return True
    except Exception:
        logger.exception("Failed to send email to %s with subject %r", to_email, subject)
        return False


def send_invite_email(to_email: str, org_name: str, inviter_name: str, token: str, role: str) -> bool:
    url = f"{settings.APP_BASE_URL}/accept-invite?token={token}"
    subject = f"You are invited to join {org_name} on Panopta"
    body = f"""
        <p>{escape(inviter_name)} invited you to join <strong>{escape(org_name)}</strong> on Panopta as a <strong>{escape(role)}</strong>.</p>
        <p>Panopta helps teams monitor data quality, catch anomalies, and coordinate incident response — with 100 eyes on your data.</p>
        {_button(url, "Accept invite")}
        <p style="font-size:14px;color:#6b7280;">This invite expires in 7 days.</p>
    """
    return _send_email(to_email, subject, _layout("Join your Panopta workspace", body))


def send_password_reset_email(to_email: str, token: str) -> bool:
    url = f"{settings.APP_BASE_URL}/reset-password?token={token}"
    subject = "Reset your Panopta password"
    body = f"""
        <p>We received a request to reset your Panopta password.</p>
        {_button(url, "Reset password")}
        <p style="font-size:14px;color:#6b7280;">This reset link expires in 1 hour. If you did not request it, you can ignore this email.</p>
    """
    return _send_email(to_email, subject, _layout("Reset your password", body))


def send_welcome_email(to_email: str, full_name: str, org_name: str) -> bool:
    subject = "Welcome to Panopta!"
    display_name = full_name or "there"
    body = f"""
        <p>Hi {escape(display_name)}, welcome to <strong>{escape(org_name)}</strong> on Panopta.</p>
        <p style="font-size:13px;color:#6b7280;font-style:italic;">"Nothing escapes the gaze of a hundred eyes."</p>
        <ol style="padding-left:20px;">
          <li>Connect your first data source.</li>
          <li>Select the tables that matter most.</li>
          <li>Review anomalies and incident reports with your team.</li>
        </ol>
        <p>You can now sign in and start monitoring your workspace.</p>
    """
    return _send_email(to_email, subject, _layout("Welcome to Panopta", body))

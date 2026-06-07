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


def send_incident_assigned_email(
    to_email: str, user_name: str, incident_title: str,
    severity: str, incident_url: str
) -> bool:
    subject = f"[Panopta] Incident assigned to you: {severity} — {incident_title[:60]}"
    sev_color = "#dc2626" if severity == "P1" else "#f97316" if severity == "P2" else "#eab308"
    body = f"""
        <div style="display:inline-block;background:{sev_color};color:white;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700;margin-bottom:12px;">{escape(severity)}</div>
        <p>Hi {escape(user_name)},</p>
        <p>An incident has been assigned to you:</p>
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0;">
          <strong>{escape(incident_title)}</strong>
        </div>
        {_button(incident_url, "View Incident →")}
        <p style="font-size:13px;color:#6b7280;">You can acknowledge, investigate, or resolve this incident from the Panopta dashboard.</p>
    """
    return _send_email(to_email, subject, _layout(f"{severity} Incident Assigned", body))


def send_team_incident_email(
    to_emails: list[str], team_name: str, incident_title: str,
    severity: str, assignee_name: str | None, incident_url: str
) -> bool:
    subject = f"[Panopta] {severity} incident assigned to {team_name}: {incident_title[:50]}"
    sev_color = "#dc2626" if severity == "P1" else "#f97316" if severity == "P2" else "#eab308"
    assignee_line = f"<p>Assigned to: <strong>{escape(assignee_name)}</strong></p>" if assignee_name else ""
    body = f"""
        <div style="display:inline-block;background:{sev_color};color:white;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700;margin-bottom:12px;">{escape(severity)}</div>
        <p>Your team <strong>{escape(team_name)}</strong> has received a new incident:</p>
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0;">
          <strong>{escape(incident_title)}</strong>
          {assignee_line}
        </div>
        {_button(incident_url, "View Incident →")}
    """
    results = [_send_email(email, subject, _layout(f"New {severity} Incident for {team_name}", body)) for email in to_emails]
    return all(results)


def send_incident_status_change_email(
    to_email: str, user_name: str, incident_title: str,
    old_status: str, new_status: str, incident_url: str
) -> bool:
    subject = f"[Panopta] Incident {new_status}: {incident_title[:60]}"
    body = f"""
        <p>Hi {escape(user_name)},</p>
        <p>An incident you are involved with has been updated:</p>
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0;">
          <strong>{escape(incident_title)}</strong>
          <p style="margin:8px 0 0 0;font-size:14px;color:#6b7280;">
            Status changed: <strong>{escape(old_status)}</strong> → <strong>{escape(new_status)}</strong>
          </p>
        </div>
        {_button(incident_url, "View Incident →")}
    """
    return _send_email(to_email, subject, _layout(f"Incident {new_status.title()}", body))


def send_member_joined_email(
    to_emails: list[str], org_name: str, new_member_name: str,
    new_member_email: str, new_member_role: str
) -> bool:
    subject = f"{new_member_name} joined {org_name} on Panopta"
    body = f"""
        <p>A new member has joined your workspace:</p>
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:16px 0;">
          <strong>{escape(new_member_name)}</strong><br>
          <span style="color:#6b7280;">{escape(new_member_email)}</span><br>
          <span style="font-size:13px;margin-top:4px;display:block;">Role: <strong>{escape(new_member_role)}</strong></span>
        </div>
        <p style="font-size:13px;color:#6b7280;">You can manage team members in Settings → Team.</p>
    """
    results = [_send_email(email, subject, _layout(f"New member in {org_name}", body)) for email in to_emails]
    return all(results)


def send_daily_digest_email(
    to_email: str, user_name: str, org_name: str,
    stats: dict, incidents: list[dict], dashboard_url: str
) -> bool:
    from datetime import date
    today = date.today().strftime("%B %d, %Y")
    subject = f"[Panopta] Daily digest — {org_name} ({today})"

    # Stats row
    p1 = stats.get("p1_open", 0)
    p2 = stats.get("p2_open", 0)
    p3 = stats.get("p3_open", 0)
    resolved = stats.get("resolved_today", 0)

    stats_html = f"""
    <div style="display:flex;gap:12px;margin:16px 0;flex-wrap:wrap;">
      <div style="border:1px solid #fca5a5;border-radius:8px;padding:12px 16px;background:#fef2f2;flex:1;min-width:80px;text-align:center;">
        <div style="font-size:24px;font-weight:900;color:#dc2626;">{p1}</div>
        <div style="font-size:11px;color:#6b7280;">P1 Open</div>
      </div>
      <div style="border:1px solid #fdba74;border-radius:8px;padding:12px 16px;background:#fff7ed;flex:1;min-width:80px;text-align:center;">
        <div style="font-size:24px;font-weight:900;color:#f97316;">{p2}</div>
        <div style="font-size:11px;color:#6b7280;">P2 Open</div>
      </div>
      <div style="border:1px solid #d1d5db;border-radius:8px;padding:12px 16px;background:#f9fafb;flex:1;min-width:80px;text-align:center;">
        <div style="font-size:24px;font-weight:900;">{p3}</div>
        <div style="font-size:11px;color:#6b7280;">P3 Open</div>
      </div>
      <div style="border:1px solid #86efac;border-radius:8px;padding:12px 16px;background:#f0fdf4;flex:1;min-width:80px;text-align:center;">
        <div style="font-size:24px;font-weight:900;color:#16a34a;">{resolved}</div>
        <div style="font-size:11px;color:#6b7280;">Resolved Today</div>
      </div>
    </div>
    """

    # Top incidents list (max 10)
    incidents_html = ""
    for inc in incidents[:10]:
        sev = inc.get("severity", "P3")
        sev_color = "#dc2626" if sev == "P1" else "#f97316" if sev == "P2" else "#6b7280"
        incidents_html += f"""
        <div style="border-bottom:1px solid #f3f4f6;padding:10px 0;">
          <span style="color:{sev_color};font-weight:700;font-size:12px;">{escape(sev)}</span>
          <span style="margin-left:8px;font-size:14px;">{escape(inc.get('title','Incident')[:80])}</span>
        </div>
        """

    body = f"""
        <p>Hi {escape(user_name)},</p>
        <p>Here's your daily data quality digest for <strong>{escape(org_name)}</strong>:</p>
        {stats_html}
        {"<h3 style='margin:16px 0 8px'>Open Incidents</h3>" + incidents_html if incidents else "<p style='color:#6b7280;'>No open incidents. All clear!</p>"}
        {_button(dashboard_url, "Open Dashboard →")}
        <p style="font-size:12px;color:#9ca3af;">You're receiving this because you enabled daily digest in Panopta notification settings.</p>
    """
    return _send_email(to_email, subject, _layout(f"Daily Digest — {org_name}", body))

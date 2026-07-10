"""Email notification service via SMTP.

All email settings are configured via environment variables (SMTP_HOST, etc.).
If SMTP is not configured, all send operations log a warning and return silently.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from scraper.logging import get_logger

logger = get_logger("api.email")

SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@aigenis.by")
APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://app.aigenis.by")


def is_smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def _send_email(to: str, subject: str, html: str) -> bool:
    if not is_smtp_configured():
        logger.warning("email_not_sent_smtp_not_configured", to=to, subject=subject)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        logger.info("email_sent", to=to, subject=subject)
        return True
    except Exception as exc:
        logger.error("email_send_failed", to=to, subject=subject, error=str(exc))
        return False


def _base_html(body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          margin: 0; padding: 0; background: #0a0a0f; color: #e5e5e5; }}
  .container {{ max-width: 600px; margin: 0 auto; padding: 24px; }}
  .card {{ background: #1a1a2e; border-radius: 12px; padding: 32px; border: 1px solid #2a2a3e; }}
  .btn {{ display: inline-block; background: #059669; color: white !important; text-decoration: none;
          padding: 12px 24px; border-radius: 8px; font-weight: 600; }}
  .btn:hover {{ background: #047857; }}
  h1 {{ font-size: 24px; margin: 0 0 16px; }}
  p {{ color: #9ca3af; line-height: 1.6; margin: 0 0 16px; }}
  .footer {{ margin-top: 32px; font-size: 12px; color: #6b7280; text-align: center; }}
</style></head><body>
<div class="container"><div class="card">
  <h1>Aigenis Bonds</h1>
  {body}
</div><div class="footer">&copy; 2026 Aigenis Parser. All rights reserved.</div></div></body></html>"""


def send_verification_email(to: str, token: str) -> bool:
    url = f"{APP_BASE_URL}/auth/verify?token={token}"
    html = _base_html(f"""
        <p>Welcome to Aigenis Bonds! Please verify your email address to activate your account.</p>
        <p style="text-align:center"><a href="{url}" class="btn">Verify Email</a></p>
        <p>Or copy this link into your browser: <code style="color:#9ca3af">{url}</code></p>
    """)
    return _send_email(to, "Verify your email — Aigenis Bonds", html)


def send_password_reset_email(to: str, token: str) -> bool:
    url = f"{APP_BASE_URL}/auth/reset-password?token={token}"
    html = _base_html(f"""
        <p>We received a request to reset your password. Click the button below to set a new one.</p>
        <p style="text-align:center"><a href="{url}" class="btn">Reset Password</a></p>
        <p>If you did not request this, you can safely ignore this email.</p>
        <p>Or copy this link: <code style="color:#9ca3af">{url}</code></p>
    """)
    return _send_email(to, "Password reset — Aigenis Bonds", html)


def send_subscription_expiring_email(to: str, tier: str, days_left: int) -> bool:
    url = f"{APP_BASE_URL}/subscribe"
    html = _base_html(f"""
        <p>Your <b>{tier}</b> subscription will expire in <b>{days_left} day{'s' if days_left != 1 else ''}</b>.</p>
        <p>Renew now to keep access to all Pro/Enterprise features without interruption.</p>
        <p style="text-align:center"><a href="{url}" class="btn">Renew Subscription</a></p>
    """)
    return _send_email(to, "Subscription expiring - Aigenis Bonds", html)


def send_welcome_email(to: str, name: str) -> bool:
    url = f"{APP_BASE_URL}"
    html = _base_html(f"""
        <p>Hi {name},</p>
        <p>Welcome to Aigenis Bonds! Your <b>7-day free trial</b> of Pro features is now active.</p>
        <p>Explore the platform and see how our fixed income tools can help you make better investment decisions.</p>
        <p style="text-align:center"><a href="{url}" class="btn">Go to Dashboard</a></p>
    """)
    return _send_email(to, "Welcome to Aigenis Bonds!", html)

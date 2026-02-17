"""
Email service.

Handles sending emails via SMTP using aiosmtplib for async support.
Used by the invitation flow to notify invited users.
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str) -> None:
    """Send an HTML email via the configured SMTP server."""
    message = EmailMessage()
    message["From"] = settings.SENDER_EMAIL
    message["To"] = to
    message["Subject"] = subject
    message.set_content(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.SENDER_EMAIL,
            password=settings.EMAIL_PASSWORD,
            start_tls=True,
        )
        logger.info("Email sent to %s", to)
    except Exception:
        logger.exception("Failed to send email to %s", to)
        raise


async def send_invitation_email(
    to_email: str,
    invitation_token: str,
    role_assigned: str,
) -> None:
    """
    Send an invitation email with the accept-invitation link.

    The link points to the frontend, which will call the
    POST /api/auth/accept-invitation endpoint.
    """
    invite_link = f"{settings.FRONTEND_URL}/accept-invitation?token={invitation_token}"

    subject = f"You've been invited to {settings.APP_NAME}"
    html_body = f"""\
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #2c3e50;">You're Invited!</h2>
            <p>You have been invited to join <strong>{settings.APP_NAME}</strong>
               as a <strong>{role_assigned}</strong>.</p>
            <p>Click the button below to set your password and activate your account:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{invite_link}"
                   style="background-color: #3498db; color: #fff; padding: 12px 30px;
                          text-decoration: none; border-radius: 5px; font-size: 16px;">
                    Accept Invitation
                </a>
            </div>
            <p style="color: #7f8c8d; font-size: 13px;">
                If the button doesn't work, copy and paste this link into your browser:<br>
                <a href="{invite_link}">{invite_link}</a>
            </p>
            <p style="color: #7f8c8d; font-size: 13px;">
                This invitation will expire in 72 hours.
            </p>
        </div>
    </body>
    </html>
    """

    await send_email(to_email, subject, html_body)

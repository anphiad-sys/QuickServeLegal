"""
QuickServe Legal - Email Delivery Tracking

Integrates with SendGrid for reliable email delivery tracking.
Provides webhook handlers for delivery status updates.
"""

import hashlib
import hmac
import base64
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings


class EmailStatus(str, Enum):
    """Email delivery status values."""
    PENDING = "pending"      # Email queued, not yet sent
    SENT = "sent"            # Accepted by SendGrid for delivery
    DELIVERED = "delivered"  # Accepted by recipient's mail server
    OPENED = "opened"        # Recipient opened email (tracking pixel)
    CLICKED = "clicked"      # Recipient clicked a link
    BOUNCED = "bounced"      # Rejected by recipient's mail server
    FAILED = "failed"        # Permanent delivery failure
    DEFERRED = "deferred"    # Temporary delivery issue, will retry
    SPAM = "spam"            # Marked as spam by recipient


# SendGrid event type to our status mapping
SENDGRID_EVENT_MAP = {
    "processed": EmailStatus.SENT,
    "dropped": EmailStatus.FAILED,
    "delivered": EmailStatus.DELIVERED,
    "bounce": EmailStatus.BOUNCED,
    "blocked": EmailStatus.BOUNCED,
    "open": EmailStatus.OPENED,
    "click": EmailStatus.CLICKED,
    "spam_report": EmailStatus.SPAM,
    "unsubscribe": EmailStatus.SPAM,
    "deferred": EmailStatus.DEFERRED,
}


def verify_sendgrid_webhook_signature(
    payload: bytes,
    signature: str,
    timestamp: str,
) -> bool:
    """
    Verify SendGrid webhook signature to ensure authenticity.

    Args:
        payload: Raw request body bytes
        signature: X-Twilio-Email-Event-Webhook-Signature header
        timestamp: X-Twilio-Email-Event-Webhook-Timestamp header

    Returns:
        True if signature is valid, False otherwise
    """
    if not settings.SENDGRID_WEBHOOK_SECRET:
        # No secret configured, skip verification in development
        return True

    # SendGrid uses ECDSA signature verification
    # For simplicity, we'll use HMAC verification if using a simple secret
    # In production, use proper ECDSA verification with SendGrid's public key

    try:
        verification_key = settings.SENDGRID_WEBHOOK_SECRET.encode()
        signed_payload = f"{timestamp}{payload.decode()}".encode()
        expected_signature = hmac.new(
            verification_key,
            signed_payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)
    except Exception:
        return False


async def update_document_email_status(
    db: AsyncSession,
    message_id: str,
    event_type: str,
    event_data: dict,
) -> bool:
    """
    Update document email status based on SendGrid webhook event.

    Args:
        db: Database session
        message_id: SendGrid message ID (sg_message_id)
        event_type: SendGrid event type (delivered, opened, etc.)
        event_data: Full event data from webhook

    Returns:
        True if document was found and updated, False otherwise
    """
    from src.models.document import Document
    from sqlalchemy import select
    from src.audit import log_event
    from src.models.audit import AuditEventType

    # Find document by message ID
    result = await db.execute(
        select(Document).where(Document.email_message_id == message_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        return False

    # Get new status
    new_status = SENDGRID_EVENT_MAP.get(event_type)
    if not new_status:
        return False

    # Get timestamp from event
    event_timestamp = datetime.utcnow()
    if "timestamp" in event_data:
        try:
            event_timestamp = datetime.fromtimestamp(event_data["timestamp"])
        except (ValueError, TypeError):
            pass

    # Update document based on event type
    old_status = document.email_status
    document.email_status = new_status.value

    if event_type == "delivered":
        document.email_delivered_at = event_timestamp
    elif event_type == "open":
        document.email_opened_at = event_timestamp
    elif event_type == "click":
        document.email_clicked_at = event_timestamp
    elif event_type in ("bounce", "blocked"):
        document.email_bounced_at = event_timestamp
        document.email_bounce_reason = event_data.get("reason", "Unknown reason")

    await db.commit()

    # Log the event
    await log_event(
        db=db,
        event_type=AuditEventType.EMAIL_STATUS_UPDATED,
        description=f"Email status updated: {old_status} → {new_status.value}",
        document_id=document.id,
        metadata={
            "sendgrid_event": event_type,
            "message_id": message_id,
            "old_status": old_status,
            "new_status": new_status.value,
        },
    )

    # If delivered, this is our ECTA Section 23 proof
    if event_type == "delivered" and not document.served_at:
        document.served_at = event_timestamp
        await db.commit()

        await log_event(
            db=db,
            event_type=AuditEventType.DOCUMENT_SERVED,
            description=f"Service confirmed: Email delivered to recipient's mail server (ECTA Section 23)",
            document_id=document.id,
            metadata={
                "delivery_timestamp": event_timestamp.isoformat(),
                "message_id": message_id,
            },
        )

    return True


async def send_email_sendgrid(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    attachment_path=None,
    attachment_filename: Optional[str] = None,
    custom_args: Optional[dict] = None,
) -> tuple[bool, Optional[str]]:
    """
    Send email using SendGrid API.

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email body
        text_content: Plain text email body (optional)
        attachment_path: Path to file to attach (optional)
        attachment_filename: Filename for attachment (optional)
        custom_args: Custom arguments for tracking (optional)

    Returns:
        Tuple of (success: bool, message_id: Optional[str])
    """
    if not settings.SENDGRID_API_KEY:
        print("SendGrid API key not configured, falling back to console output")
        return _log_email_to_console(to_email, subject, html_content, text_content, attachment_path, attachment_filename)

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, Attachment, FileContent, FileName,
            FileType, Disposition, TrackingSettings,
            OpenTracking, ClickTracking
        )
        import base64

        # Create message
        message = Mail(
            from_email=(settings.SMTP_FROM_EMAIL, settings.SMTP_FROM_NAME),
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )

        if text_content:
            message.plain_text_content = text_content

        # Add attachment if provided
        if attachment_path and attachment_path.exists():
            with open(attachment_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode()

            attachment = Attachment(
                FileContent(file_data),
                FileName(attachment_filename or attachment_path.name),
                FileType("application/pdf"),
                Disposition("attachment"),
            )
            message.attachment = attachment

        # Configure tracking
        tracking_settings = TrackingSettings()
        if settings.EMAIL_OPEN_TRACKING:
            tracking_settings.open_tracking = OpenTracking(
                enable=True,
                substitution_tag=None
            )
        if settings.EMAIL_CLICK_TRACKING:
            tracking_settings.click_tracking = ClickTracking(
                enable=True,
                enable_text=False
            )
        message.tracking_settings = tracking_settings

        # Add custom arguments for webhook correlation
        if custom_args:
            for key, value in custom_args.items():
                message.custom_arg = (key, str(value))

        # Send email
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)

        # Extract message ID from response headers
        message_id = None
        if hasattr(response, 'headers') and 'X-Message-Id' in response.headers:
            message_id = response.headers['X-Message-Id']

        if response.status_code in (200, 201, 202):
            return True, message_id
        else:
            print(f"SendGrid error: {response.status_code} - {response.body}")
            return False, None

    except ImportError:
        print("SendGrid package not installed. Install with: pip install sendgrid")
        return _log_email_to_console(to_email, subject, html_content, text_content, attachment_path, attachment_filename)
    except Exception as e:
        print(f"SendGrid error: {e}")
        return False, None


def _log_email_to_console(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str],
    attachment_path,
    attachment_filename: Optional[str],
) -> tuple[bool, Optional[str]]:
    """Log email to console for development mode."""
    import uuid

    # Generate mock message ID for development
    mock_message_id = f"dev-{uuid.uuid4().hex[:16]}"

    print("\n" + "=" * 60)
    print("EMAIL NOTIFICATION (Development Mode)")
    print("=" * 60)
    print(f"To: {to_email}")
    print(f"Subject: {subject}")
    print(f"Message ID: {mock_message_id}")
    if attachment_path:
        print(f"Attachment: {attachment_filename or attachment_path.name}")
        if hasattr(attachment_path, 'stat'):
            print(f"Attachment Size: {attachment_path.stat().st_size:,} bytes")
    print("-" * 60)
    if text_content:
        print(text_content[:500] + "..." if len(text_content) > 500 else text_content)
    else:
        print(html_content[:500] + "..." if len(html_content) > 500 else html_content)
    print("=" * 60 + "\n")

    return True, mock_message_id


def get_email_status_badge_class(status: str) -> str:
    """Get CSS class for email status badge."""
    class_map = {
        "pending": "bg-gray-100 text-gray-800",
        "sent": "bg-blue-100 text-blue-800",
        "delivered": "bg-green-100 text-green-800",
        "opened": "bg-green-100 text-green-800",
        "clicked": "bg-green-100 text-green-800",
        "bounced": "bg-red-100 text-red-800",
        "failed": "bg-red-100 text-red-800",
        "deferred": "bg-yellow-100 text-yellow-800",
        "spam": "bg-red-100 text-red-800",
    }
    return class_map.get(status, "bg-gray-100 text-gray-800")


def get_email_status_icon(status: str) -> str:
    """Get icon name for email status."""
    icon_map = {
        "pending": "clock",
        "sent": "paper-airplane",
        "delivered": "check-circle",
        "opened": "eye",
        "clicked": "cursor-click",
        "bounced": "x-circle",
        "failed": "x-circle",
        "deferred": "clock",
        "spam": "exclamation-circle",
    }
    return icon_map.get(status, "question-mark-circle")

"""
QuickServe Legal - Email Notification System

Handles email notifications with PDF attachments for ECTA-compliant service.
Per ECTA Section 23, the actual document (data message) must enter the
recipient's information system for service to be complete.

Supports two email providers:
- SMTP (development/basic production)
- SendGrid (production with delivery tracking)
"""

import aiosmtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from src.config import settings
from src.models.document import Document


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    attachment_path: Optional[Path] = None,
    attachment_filename: Optional[str] = None,
    custom_args: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Send an email, optionally with a PDF attachment.

    Returns a tuple of (success, message_id) where message_id can be used
    for delivery tracking with SendGrid webhooks.

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email body
        text_content: Plain text email body (optional)
        attachment_path: Path to file to attach (optional)
        attachment_filename: Filename to use for attachment (optional)
        custom_args: Custom arguments for tracking (optional)

    Returns:
        Tuple of (success: bool, message_id: Optional[str])
    """
    # Use SendGrid if configured
    if settings.EMAIL_PROVIDER == "sendgrid" and settings.SENDGRID_API_KEY:
        from src.email_tracking import send_email_sendgrid
        return await send_email_sendgrid(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            attachment_path=attachment_path,
            attachment_filename=attachment_filename,
            custom_args=custom_args,
        )

    # Development mode - log to console
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
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
            print(f"Attachment Size: {attachment_path.stat().st_size:,} bytes")
        print("-" * 60)
        print(text_content or html_content[:500] + "..." if len(html_content) > 500 else html_content)
        print("=" * 60 + "\n")
        return True, mock_message_id

    # Production mode - send via SMTP
    try:
        # Generate a message ID for tracking
        message_id = f"smtp-{uuid.uuid4().hex}"

        # Use mixed multipart for attachments
        message = MIMEMultipart("mixed")
        message["Subject"] = subject
        message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        message["To"] = to_email
        message["Message-ID"] = f"<{message_id}@quickservelegal.co.za>"

        # Create alternative part for text/html body
        body_part = MIMEMultipart("alternative")

        # Add text part
        if text_content:
            body_part.attach(MIMEText(text_content, "plain"))

        # Add HTML part
        body_part.attach(MIMEText(html_content, "html"))

        message.attach(body_part)

        # Add PDF attachment if provided
        if attachment_path and attachment_path.exists():
            with open(attachment_path, "rb") as f:
                pdf_data = f.read()

            pdf_attachment = MIMEApplication(pdf_data, _subtype="pdf")
            filename = attachment_filename or attachment_path.name
            pdf_attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=filename
            )
            message.attach(pdf_attachment)

        # Send email
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        return True, message_id

    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False, None


# =============================================================================
# NOTIFICATION TEMPLATES
# =============================================================================

def get_document_notification_email(document: Document, download_url: str) -> tuple[str, str, str]:
    """
    Generate email content for notifying recipient of a new document.

    The actual PDF document is attached to this email (ECTA-compliant service).
    A backup download link is also provided.

    Returns: (subject, html_content, text_content)
    """
    subject = f"Legal Document Served: {document.original_filename} - from {document.sender_name}"

    matter_info = ""
    if document.matter_reference:
        matter_info = f"<p><strong>Matter Reference:</strong> {document.matter_reference}</p>"

    description_info = ""
    if document.description:
        description_info = f"<p><strong>Notes:</strong> {document.description}</p>"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #fff; padding: 30px; border: 1px solid #e5e7eb; }}
            .document-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .attachment-notice {{ background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 15px; margin: 20px 0; }}
            .button {{ display: inline-block; background: #6b7280; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 10px 0; font-size: 12px; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; }}
            .legal-notice {{ font-size: 11px; color: #6b7280; margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0;">QuickServe Legal</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Electronic Service of Legal Documents</p>
            </div>
            <div class="content">
                <h2 style="margin-top: 0;">A Legal Document Has Been Served on You</h2>

                <p><strong>{document.sender_name}</strong> ({document.sender_email}) has served you a legal document via QuickServe Legal.</p>

                <div class="attachment-notice">
                    <p style="margin: 0; color: #065f46;"><strong>📎 Document Attached:</strong> The served document <strong>{document.original_filename}</strong> is attached to this email.</p>
                </div>

                <div class="document-box">
                    <p style="margin: 0;"><strong>Document:</strong> {document.original_filename}</p>
                    {matter_info}
                    {description_info}
                    <p style="margin: 0;"><strong>Served on:</strong> {document.created_at.strftime('%d %B %Y at %H:%M')} SAST</p>
                    <p style="margin: 0;"><strong>File Size:</strong> {document.file_size:,} bytes</p>
                </div>

                <p style="font-size: 12px; color: #6b7280;">
                    <strong>Backup download:</strong> If you cannot access the attachment, you may also download the document using the link below (expires {document.token_expires_at.strftime('%d %B %Y')}):<br/>
                    <a href="{download_url}" class="button">Download from Server</a>
                </p>

                <div class="legal-notice">
                    <p><strong>Legal Notice:</strong> This document has been served electronically in accordance with
                    Section 23 of the Electronic Communications and Transactions Act 25 of 2002 (ECTA) and
                    Rule 4A of the Uniform Rules of Court.</p>
                    <p>Service is deemed complete upon this email entering your information system.</p>
                </div>
            </div>
            <div class="footer">
                <p>This email was sent via QuickServe Legal - Electronic Service of Legal Documents</p>
                <p>If you believe you received this in error, please contact {document.sender_email}</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
QUICKSERVE LEGAL - Electronic Service of Legal Documents
=========================================================

A LEGAL DOCUMENT HAS BEEN SERVED ON YOU

{document.sender_name} ({document.sender_email}) has served you a legal document via QuickServe Legal.

ATTACHED DOCUMENT: {document.original_filename}
The served document is attached to this email.

DOCUMENT DETAILS:
- Document: {document.original_filename}
{f"- Matter Reference: {document.matter_reference}" if document.matter_reference else ""}
{f"- Notes: {document.description}" if document.description else ""}
- Served on: {document.created_at.strftime('%d %B %Y at %H:%M')} SAST
- File Size: {document.file_size:,} bytes

BACKUP DOWNLOAD LINK:
If you cannot access the attachment, download from: {download_url}
(Link expires: {document.token_expires_at.strftime('%d %B %Y at %H:%M')})

LEGAL NOTICE:
This document has been served electronically in accordance with Section 23 of the
Electronic Communications and Transactions Act 25 of 2002 (ECTA) and Rule 4A of
the Uniform Rules of Court.

Service is deemed complete upon this email entering your information system.

---
QuickServe Legal - Electronic Service of Legal Documents
If you believe you received this in error, please contact {document.sender_email}
    """

    return subject, html_content, text_content


def get_download_confirmation_email(document: Document) -> tuple[str, str, str]:
    """
    Generate email content for confirming document download to sender.

    Returns: (subject, html_content, text_content)
    """
    subject = f"Document Downloaded - {document.original_filename}"

    matter_info = ""
    if document.matter_reference:
        matter_info = f"<p><strong>Matter Reference:</strong> {document.matter_reference}</p>"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #059669 0%, #10b981 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #fff; padding: 30px; border: 1px solid #e5e7eb; }}
            .success-box {{ background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .details-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .button {{ display: inline-block; background: #2563eb; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 20px 0; }}
            .footer {{ background: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0;">Document Downloaded</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">Receipt Confirmed</p>
            </div>
            <div class="content">
                <div class="success-box">
                    <h2 style="margin: 0; color: #059669;">Confirmed: Document Received</h2>
                    <p style="margin: 10px 0 0 0;">Your document has been successfully downloaded by the recipient.</p>
                </div>

                <div class="details-box">
                    <p><strong>Document:</strong> {document.original_filename}</p>
                    <p><strong>Recipient:</strong> {document.recipient_email}</p>
                    {matter_info}
                    <p><strong>Served:</strong> {document.created_at.strftime('%d %B %Y at %H:%M')}</p>
                    <p><strong>Downloaded:</strong> {document.downloaded_at.strftime('%d %B %Y at %H:%M') if document.downloaded_at else 'N/A'}</p>
                </div>

                <p>A Proof of Service document is now available on your dashboard.</p>

                <p style="text-align: center;">
                    <a href="{settings.BASE_URL}/dashboard" class="button">View Dashboard</a>
                </p>
            </div>
            <div class="footer">
                <p>QuickServe Legal - Electronic Service of Legal Documents</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"""
QUICKSERVE LEGAL
==========================================

CONFIRMED: Document Downloaded

Your document has been successfully downloaded by the recipient.

DETAILS:
- Document: {document.original_filename}
- Recipient: {document.recipient_email}
{f"- Matter Reference: {document.matter_reference}" if document.matter_reference else ""}
- Served: {document.created_at.strftime('%d %B %Y at %H:%M')}
- Downloaded: {document.downloaded_at.strftime('%d %B %Y at %H:%M') if document.downloaded_at else 'N/A'}

A Proof of Service document is now available on your dashboard.

View Dashboard: {settings.BASE_URL}/dashboard

---
QuickServe Legal - Electronic Service of Legal Documents
    """

    return subject, html_content, text_content


# =============================================================================
# NOTIFICATION FUNCTIONS
# =============================================================================

async def notify_recipient_of_document(
    document: Document,
    download_url: str,
    pdf_path: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Send notification email to recipient with the document attached.

    Per ECTA Section 23, the actual document (data message) is attached to the email
    so it enters the recipient's information system upon delivery.

    Args:
        document: The Document model instance
        download_url: Backup download URL
        pdf_path: Path to the PDF file to attach

    Returns:
        Tuple of (success: bool, message_id: Optional[str])
        The message_id can be used to track delivery via SendGrid webhooks.
    """
    subject, html_content, text_content = get_document_notification_email(document, download_url)
    return await send_email(
        to_email=document.recipient_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        attachment_path=pdf_path,
        attachment_filename=document.original_filename,
        custom_args={"document_id": str(document.id)},
    )


async def notify_sender_of_download(document: Document) -> Tuple[bool, Optional[str]]:
    """Send confirmation email to sender that document was downloaded."""
    subject, html_content, text_content = get_download_confirmation_email(document)
    return await send_email(document.sender_email, subject, html_content, text_content)

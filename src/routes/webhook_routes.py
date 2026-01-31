"""
QuickServe Legal - Webhook Routes

Handles incoming webhooks from external services (SendGrid, etc.).
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import json

from src.database import get_db
from src.config import settings
from src.email_tracking import (
    verify_sendgrid_webhook_signature,
    update_document_email_status,
)


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/sendgrid")
async def sendgrid_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle SendGrid Event Webhook.

    SendGrid sends events for email delivery tracking:
    - processed: Email accepted by SendGrid
    - delivered: Email accepted by recipient's mail server
    - open: Recipient opened email
    - click: Recipient clicked a link
    - bounce: Email bounced
    - dropped: Email dropped (invalid, spam, etc.)
    - deferred: Temporary delivery issue
    - spam_report: Recipient marked as spam

    See: https://docs.sendgrid.com/for-developers/tracking-events/event
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook signature if configured
    if settings.SENDGRID_WEBHOOK_SECRET:
        signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
        timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")

        if not verify_sendgrid_webhook_signature(body, signature, timestamp):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse events
    try:
        events = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Process each event
    processed_count = 0
    for event in events:
        event_type = event.get("event")
        sg_message_id = event.get("sg_message_id")

        if not event_type or not sg_message_id:
            continue

        # Clean up message ID (SendGrid sometimes adds suffix)
        if "." in sg_message_id:
            sg_message_id = sg_message_id.split(".")[0]

        # Update document status
        success = await update_document_email_status(
            db=db,
            message_id=sg_message_id,
            event_type=event_type,
            event_data=event,
        )

        if success:
            processed_count += 1

    return JSONResponse(
        content={"status": "ok", "processed": processed_count},
        status_code=200,
    )


@router.get("/sendgrid/test")
async def sendgrid_webhook_test():
    """
    Test endpoint to verify webhook configuration.
    SendGrid may call this to verify the endpoint is reachable.
    """
    return JSONResponse(
        content={"status": "ok", "message": "SendGrid webhook endpoint is active"},
        status_code=200,
    )


# Development-only endpoint to simulate webhook events
if settings.DEBUG:
    @router.post("/sendgrid/simulate")
    async def simulate_sendgrid_event(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        """
        Simulate a SendGrid webhook event for development testing.

        POST body:
        {
            "message_id": "dev-abc123...",
            "event": "delivered"  // or "opened", "clicked", "bounced"
        }
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        message_id = data.get("message_id")
        event_type = data.get("event", "delivered")

        if not message_id:
            raise HTTPException(status_code=400, detail="message_id required")

        success = await update_document_email_status(
            db=db,
            message_id=message_id,
            event_type=event_type,
            event_data=data,
        )

        if success:
            return JSONResponse(
                content={"status": "ok", "event": event_type, "message_id": message_id},
                status_code=200,
            )
        else:
            return JSONResponse(
                content={"status": "not_found", "message": "No document found with this message_id"},
                status_code=404,
            )

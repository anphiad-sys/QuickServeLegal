"""
QuickServe Legal - PNSA Branch Routes

Web-based interface for PNSA branch operators to process walk-in document service.
"""

import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, TEMPLATES_DIR
from src.database import get_db
from src.pnsa_auth import (
    get_current_operator,
    authenticate_operator,
    update_operator_last_login,
    create_operator_session,
    get_active_branches,
    get_branch_by_id,
    PNSA_SESSION_COOKIE,
)
from src.models.branch_operator import BranchOperator
from src.models.branch import Branch
from src.models.walk_in_service import WalkInService, WalkInServiceStatus, ID_TYPES
from src.models.document import Document, DocumentSourceType
from src.models.user import User
from src.auth import get_user_by_email
from src.documents import (
    validate_file,
    generate_stored_filename,
    save_uploaded_file,
    generate_download_token,
    get_file_path,
)
from src.billing import get_service_fee, record_walk_in_service_fee, get_operator_daily_stats
from src.notifications import notify_recipient_of_document
from src.audit import log_event
from src.models.audit import AuditEventType


router = APIRouter(prefix="/pnsa", tags=["pnsa"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# =============================================================================
# AUTHENTICATION
# =============================================================================

@router.get("/login", response_class=HTMLResponse)
async def pnsa_login_page(
    request: Request,
    next: str = "/pnsa/dashboard",
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Display PNSA operator login page."""
    # Check if already logged in
    operator = await get_current_operator(request, db)
    if operator:
        return RedirectResponse(url="/pnsa/dashboard", status_code=303)

    # Get list of active branches for dropdown
    branches = await get_active_branches(db)

    return templates.TemplateResponse(
        "pnsa/login.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "next": next,
            "error": error,
            "branches": branches,
        }
    )


@router.post("/login")
async def pnsa_login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/pnsa/dashboard"),
    db: AsyncSession = Depends(get_db),
):
    """Process PNSA operator login."""
    operator = await authenticate_operator(db, email, password)

    if not operator:
        branches = await get_active_branches(db)
        return templates.TemplateResponse(
            "pnsa/login.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "error": "Invalid email or password",
                "email": email,
                "next": next,
                "branches": branches,
            },
            status_code=401,
        )

    # Check if operator's branch is active
    branch = await get_branch_by_id(db, operator.branch_id)
    if not branch or not branch.is_active:
        branches = await get_active_branches(db)
        return templates.TemplateResponse(
            "pnsa/login.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "error": "Your branch is currently inactive. Please contact support.",
                "email": email,
                "next": next,
                "branches": branches,
            },
            status_code=401,
        )

    # Update last login
    await update_operator_last_login(db, operator)

    # Log the login event
    await log_event(
        db=db,
        event_type="pnsa.operator_login",
        description=f"PNSA operator {operator.full_name} logged in at branch {branch.branch_name}",
        metadata={
            "operator_id": operator.id,
            "branch_id": branch.id,
            "branch_code": branch.branch_code,
        },
        ip_address=request.client.host if request.client else None,
    )

    # Create session and redirect
    session_token = create_operator_session(operator.id, branch.id)
    response = RedirectResponse(url=next, status_code=303)
    response.set_cookie(
        key=PNSA_SESSION_COOKIE,
        value=session_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=getattr(settings, 'PNSA_SESSION_EXPIRE_MINUTES', 480) * 60,
    )
    return response


@router.get("/logout")
async def pnsa_logout(request: Request, db: AsyncSession = Depends(get_db)):
    """Log out PNSA operator."""
    operator = await get_current_operator(request, db)
    if operator:
        branch = await get_branch_by_id(db, operator.branch_id)
        await log_event(
            db=db,
            event_type="pnsa.operator_logout",
            description=f"PNSA operator {operator.full_name} logged out",
            metadata={
                "operator_id": operator.id,
                "branch_id": operator.branch_id,
                "branch_code": branch.branch_code if branch else None,
            },
            ip_address=request.client.host if request.client else None,
        )

    response = RedirectResponse(url="/pnsa/login", status_code=303)
    response.delete_cookie(PNSA_SESSION_COOKIE)
    return response


# =============================================================================
# DASHBOARD
# =============================================================================

@router.get("/dashboard", response_class=HTMLResponse)
async def pnsa_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PNSA operator dashboard."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login?next=/pnsa/dashboard", status_code=303)

    branch = await get_branch_by_id(db, operator.branch_id)

    # Get today's stats for this operator
    daily_stats = await get_operator_daily_stats(db, operator.id)

    # Get recent services for this branch (today)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(WalkInService)
        .where(
            and_(
                WalkInService.branch_id == operator.branch_id,
                WalkInService.created_at >= today_start,
            )
        )
        .order_by(WalkInService.created_at.desc())
        .limit(20)
    )
    recent_services = list(result.scalars().all())

    return templates.TemplateResponse(
        "pnsa/dashboard.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "operator": operator,
            "branch": branch,
            "daily_stats": daily_stats,
            "recent_services": recent_services,
            "service_fee": get_service_fee(),
        }
    )


# =============================================================================
# DOCUMENT SCANNING & UPLOAD
# =============================================================================

@router.get("/scan", response_class=HTMLResponse)
async def pnsa_scan_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Display document scan/upload page."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login?next=/pnsa/scan", status_code=303)

    branch = await get_branch_by_id(db, operator.branch_id)

    return templates.TemplateResponse(
        "pnsa/scan.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "operator": operator,
            "branch": branch,
            "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        }
    )


@router.post("/scan")
async def pnsa_scan_submit(
    request: Request,
    document: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Process scanned document upload and run OCR."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login?next=/pnsa/scan", status_code=303)

    branch = await get_branch_by_id(db, operator.branch_id)

    try:
        # Validate file
        validate_file(document)

        # Generate filenames
        original_filename = document.filename or "scanned_document.pdf"
        stored_filename = generate_stored_filename(original_filename)
        download_token = generate_download_token()

        # Save file to disk
        file_size = await save_uploaded_file(document, stored_filename)

        # Get file path for OCR
        pdf_path = get_file_path(stored_filename)

        # Run OCR extraction
        ocr_data = {}
        ocr_confidence = 0.0
        try:
            from src.ocr_processor import extract_for_pnsa_service
            ocr_data = await extract_for_pnsa_service(pdf_path)
            ocr_confidence = ocr_data.get("confidence", 0.0)
        except Exception as e:
            # OCR failed but continue - operator can enter data manually
            pass

        # Create preliminary document record (will be updated after review)
        token_expires_at = datetime.utcnow() + timedelta(hours=settings.DOWNLOAD_TOKEN_EXPIRE_HOURS)

        doc = Document(
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_size=file_size,
            content_type="application/pdf",
            source_type=DocumentSourceType.PNSA,
            # Placeholder sender info (will be service account)
            sender_id=1,  # Will be updated
            sender_email="pnsa@quickservelegal.co.za",
            sender_name=f"PNSA - {branch.branch_name}",
            # Recipient from OCR (to be confirmed)
            recipient_email=ocr_data.get("recipient_attorney_email") or "pending@review.required",
            recipient_name=ocr_data.get("recipient_attorney_name"),
            # Matter details from OCR
            matter_reference=ocr_data.get("case_number"),
            description=f"{ocr_data.get('pleading_type', 'Legal Document')} - {ocr_data.get('plaintiff', '')} v {ocr_data.get('defendant', '')}".strip(" -"),
            # Token
            download_token=download_token,
            token_expires_at=token_expires_at,
            status="pending",
            # OCR data
            ocr_plaintiff=ocr_data.get("plaintiff"),
            ocr_defendant=ocr_data.get("defendant"),
            ocr_case_number=ocr_data.get("case_number"),
            ocr_court_name=ocr_data.get("court_name"),
            ocr_pleading_type=ocr_data.get("pleading_type"),
            ocr_confidence=ocr_confidence,
        )

        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # Create walk-in service record
        walk_in = WalkInService(
            document_id=doc.id,
            branch_id=operator.branch_id,
            operator_id=operator.id,
            # Messenger details (to be filled)
            messenger_name="",
            messenger_id_number="",
            messenger_id_type="RSA ID",
            # Serving attorney from OCR
            serving_attorney_name=ocr_data.get("serving_attorney_name") or "",
            serving_attorney_firm=ocr_data.get("serving_attorney_firm"),
            serving_attorney_email=ocr_data.get("serving_attorney_email"),
            serving_attorney_phone=ocr_data.get("serving_attorney_phone"),
            serving_attorney_address=ocr_data.get("serving_attorney_address"),
            # Billing (to be set after recipient is confirmed)
            billed_to_member_id=1,  # Placeholder
            service_fee=get_service_fee(),
            billing_status="pending",
            # Status
            status=WalkInServiceStatus.PENDING,
            ocr_confidence=ocr_confidence,
            scanned_at=datetime.utcnow(),
        )

        db.add(walk_in)
        await db.commit()
        await db.refresh(walk_in)

        # Log the scan event
        await log_event(
            db=db,
            event_type="pnsa.document_scanned",
            description=f"Document scanned at {branch.branch_name} by {operator.full_name}",
            document_id=doc.id,
            metadata={
                "walk_in_service_id": walk_in.id,
                "branch_id": branch.id,
                "operator_id": operator.id,
                "ocr_confidence": ocr_confidence,
            },
            ip_address=request.client.host if request.client else None,
        )

        # Redirect to document review page
        return RedirectResponse(
            url=f"/pnsa/document/{walk_in.id}",
            status_code=303
        )

    except HTTPException as e:
        return templates.TemplateResponse(
            "pnsa/scan.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "operator": operator,
                "branch": branch,
                "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
                "error": e.detail,
            },
            status_code=400,
        )


# =============================================================================
# DOCUMENT REVIEW & UPDATE
# =============================================================================

@router.get("/document/{walk_in_id}", response_class=HTMLResponse)
async def pnsa_document_review(
    request: Request,
    walk_in_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Display document review page with OCR extracted data."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login", status_code=303)

    # Get walk-in service and document
    result = await db.execute(
        select(WalkInService).where(WalkInService.id == walk_in_id)
    )
    walk_in = result.scalar_one_or_none()

    if not walk_in or walk_in.branch_id != operator.branch_id:
        raise HTTPException(status_code=404, detail="Service record not found")

    result = await db.execute(
        select(Document).where(Document.id == walk_in.document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    branch = await get_branch_by_id(db, operator.branch_id)

    # Check if recipient email belongs to a QSL member
    recipient_member = None
    if doc.recipient_email and doc.recipient_email != "pending@review.required":
        recipient_member = await get_user_by_email(db, doc.recipient_email)

    return templates.TemplateResponse(
        "pnsa/document_review.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "operator": operator,
            "branch": branch,
            "walk_in": walk_in,
            "document": doc,
            "recipient_member": recipient_member,
            "service_fee": get_service_fee(),
            "id_types": ID_TYPES,
        }
    )


@router.post("/document/{walk_in_id}/update")
async def pnsa_document_update(
    request: Request,
    walk_in_id: int,
    # Recipient details
    recipient_email: str = Form(...),
    recipient_name: str = Form(None),
    # Case details
    case_number: str = Form(None),
    court_name: str = Form(None),
    pleading_type: str = Form(None),
    plaintiff: str = Form(None),
    defendant: str = Form(None),
    # Serving attorney
    serving_attorney_name: str = Form(...),
    serving_attorney_firm: str = Form(None),
    serving_attorney_email: str = Form(None),
    serving_attorney_phone: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Update document and walk-in service details after operator review."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login", status_code=303)

    # Get walk-in service
    result = await db.execute(
        select(WalkInService).where(WalkInService.id == walk_in_id)
    )
    walk_in = result.scalar_one_or_none()

    if not walk_in or walk_in.branch_id != operator.branch_id:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == walk_in.document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify recipient is a QSL member
    recipient_member = await get_user_by_email(db, recipient_email)
    if not recipient_member:
        branch = await get_branch_by_id(db, operator.branch_id)
        return templates.TemplateResponse(
            "pnsa/document_review.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "operator": operator,
                "branch": branch,
                "walk_in": walk_in,
                "document": doc,
                "recipient_member": None,
                "service_fee": get_service_fee(),
                "id_types": ID_TYPES,
                "error": f"No QSL member found with email: {recipient_email}. The recipient must be a registered QSL member.",
            },
            status_code=400,
        )

    # Update document
    doc.recipient_email = recipient_email.lower().strip()
    doc.recipient_name = recipient_name.strip() if recipient_name else recipient_member.full_name
    doc.matter_reference = case_number.strip() if case_number else None
    doc.ocr_case_number = case_number.strip() if case_number else None
    doc.ocr_court_name = court_name.strip() if court_name else None
    doc.ocr_pleading_type = pleading_type.strip() if pleading_type else None
    doc.ocr_plaintiff = plaintiff.strip() if plaintiff else None
    doc.ocr_defendant = defendant.strip() if defendant else None

    # Build description
    desc_parts = []
    if pleading_type:
        desc_parts.append(pleading_type.strip())
    if plaintiff and defendant:
        desc_parts.append(f"{plaintiff.strip()} v {defendant.strip()}")
    doc.description = " - ".join(desc_parts) if desc_parts else None

    # Update walk-in service
    walk_in.serving_attorney_name = serving_attorney_name.strip()
    walk_in.serving_attorney_firm = serving_attorney_firm.strip() if serving_attorney_firm else None
    walk_in.serving_attorney_email = serving_attorney_email.strip() if serving_attorney_email else None
    walk_in.serving_attorney_phone = serving_attorney_phone.strip() if serving_attorney_phone else None
    walk_in.billed_to_member_id = recipient_member.id
    walk_in.reviewed_at = datetime.utcnow()
    walk_in.status = WalkInServiceStatus.REVIEWED

    await db.commit()

    # Redirect to messenger form
    return RedirectResponse(
        url=f"/pnsa/document/{walk_in_id}/messenger",
        status_code=303
    )


# =============================================================================
# MESSENGER CONFIRMATION
# =============================================================================

@router.get("/document/{walk_in_id}/messenger", response_class=HTMLResponse)
async def pnsa_messenger_form(
    request: Request,
    walk_in_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Display messenger ID confirmation form."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login", status_code=303)

    # Get walk-in service
    result = await db.execute(
        select(WalkInService).where(WalkInService.id == walk_in_id)
    )
    walk_in = result.scalar_one_or_none()

    if not walk_in or walk_in.branch_id != operator.branch_id:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == walk_in.document_id)
    )
    doc = result.scalar_one_or_none()

    branch = await get_branch_by_id(db, operator.branch_id)

    return templates.TemplateResponse(
        "pnsa/messenger_form.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "operator": operator,
            "branch": branch,
            "walk_in": walk_in,
            "document": doc,
            "id_types": ID_TYPES,
            "service_fee": get_service_fee(),
        }
    )


@router.post("/document/{walk_in_id}/serve")
async def pnsa_serve_document(
    request: Request,
    walk_in_id: int,
    messenger_name: str = Form(...),
    messenger_id_number: str = Form(...),
    messenger_id_type: str = Form("RSA ID"),
    operator_notes: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Confirm service - capture messenger ID and serve document."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login", status_code=303)

    # Get walk-in service
    result = await db.execute(
        select(WalkInService).where(WalkInService.id == walk_in_id)
    )
    walk_in = result.scalar_one_or_none()

    if not walk_in or walk_in.branch_id != operator.branch_id:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Check if already served
    if walk_in.is_served:
        return RedirectResponse(
            url=f"/pnsa/document/{walk_in_id}/print",
            status_code=303
        )

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == walk_in.document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    branch = await get_branch_by_id(db, operator.branch_id)

    # Update messenger details
    walk_in.messenger_name = messenger_name.strip()
    walk_in.messenger_id_number = messenger_id_number.strip()
    walk_in.messenger_id_type = messenger_id_type
    walk_in.operator_notes = operator_notes.strip() if operator_notes else None

    # Get recipient member
    recipient_member = await get_user_by_email(db, doc.recipient_email)
    if not recipient_member:
        raise HTTPException(status_code=400, detail="Recipient member not found")

    # Update document sender info (now that we have confirmed details)
    doc.sender_email = f"pnsa.{branch.branch_code.lower()}@quickservelegal.co.za"
    doc.sender_name = f"PNSA {branch.branch_name} - {walk_in.serving_attorney_name}"

    # Send notification email to recipient
    download_url = f"{settings.BASE_URL}/download/{doc.download_token}"
    pdf_path = get_file_path(doc.stored_filename)

    notification_sent, message_id = await notify_recipient_of_document(
        doc,
        download_url,
        pdf_path,
    )

    if notification_sent:
        # Mark document as served
        doc.status = "served"
        doc.served_at = datetime.utcnow()
        doc.notified_at = datetime.utcnow()
        if message_id:
            doc.email_message_id = message_id
            doc.email_status = "sent"

        # Update walk-in service
        walk_in.served_at = datetime.utcnow()
        walk_in.status = WalkInServiceStatus.SERVED

        # Record billing
        await record_walk_in_service_fee(
            db,
            walk_in,
            recipient_member.id,
            get_service_fee(),
        )

        await db.commit()

        # Log the service event
        await log_event(
            db=db,
            event_type="pnsa.document_served",
            description=f"Document served via PNSA {branch.branch_name} to {doc.recipient_email}",
            document_id=doc.id,
            metadata={
                "walk_in_service_id": walk_in.id,
                "branch_id": branch.id,
                "operator_id": operator.id,
                "messenger_name": walk_in.messenger_name,
                "serving_attorney": walk_in.serving_attorney_name,
                "recipient_member_id": recipient_member.id,
                "service_fee": str(walk_in.service_fee),
            },
            ip_address=request.client.host if request.client else None,
        )

        return RedirectResponse(
            url=f"/pnsa/document/{walk_in_id}/print",
            status_code=303
        )
    else:
        # Email failed
        return templates.TemplateResponse(
            "pnsa/messenger_form.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "operator": operator,
                "branch": branch,
                "walk_in": walk_in,
                "document": doc,
                "id_types": ID_TYPES,
                "service_fee": get_service_fee(),
                "error": "Failed to send notification email. Please try again or contact support.",
                "messenger_name": messenger_name,
                "messenger_id_number": messenger_id_number,
                "messenger_id_type": messenger_id_type,
            },
            status_code=500,
        )


# =============================================================================
# PRINT CONFIRMATION
# =============================================================================

@router.get("/document/{walk_in_id}/print", response_class=HTMLResponse)
async def pnsa_print_confirmation(
    request: Request,
    walk_in_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Display print-optimized confirmation page."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login", status_code=303)

    # Get walk-in service
    result = await db.execute(
        select(WalkInService).where(WalkInService.id == walk_in_id)
    )
    walk_in = result.scalar_one_or_none()

    if not walk_in or walk_in.branch_id != operator.branch_id:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Get document
    result = await db.execute(
        select(Document).where(Document.id == walk_in.document_id)
    )
    doc = result.scalar_one_or_none()

    branch = await get_branch_by_id(db, operator.branch_id)

    # Mark confirmation as printed
    if not walk_in.confirmations_printed_at:
        walk_in.confirmations_printed_at = datetime.utcnow()
        walk_in.status = WalkInServiceStatus.COMPLETED
        await db.commit()

    return templates.TemplateResponse(
        "pnsa/print_confirmation.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "operator": operator,
            "branch": branch,
            "walk_in": walk_in,
            "document": doc,
            "service_fee": get_service_fee(),
        }
    )


@router.post("/document/{walk_in_id}/mark-printed")
async def pnsa_mark_printed(
    request: Request,
    walk_in_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mark confirmation as printed and return to dashboard."""
    operator = await get_current_operator(request, db)
    if not operator:
        return RedirectResponse(url="/pnsa/login", status_code=303)

    # Get walk-in service
    result = await db.execute(
        select(WalkInService).where(WalkInService.id == walk_in_id)
    )
    walk_in = result.scalar_one_or_none()

    if not walk_in or walk_in.branch_id != operator.branch_id:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Mark as printed if not already
    if not walk_in.confirmations_printed_at:
        walk_in.confirmations_printed_at = datetime.utcnow()
        walk_in.status = WalkInServiceStatus.COMPLETED
        await db.commit()

    return RedirectResponse(url="/pnsa/dashboard", status_code=303)

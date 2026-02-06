"""
QuickServe Legal - Document Routes
"""

import tempfile
import os
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, TEMPLATES_DIR
from src.database import get_db
from src.auth import get_current_user
from src.models.user import User
from src.documents import (
    create_document,
    get_document_by_token,
    get_document_by_id,
    get_user_sent_documents,
    get_file_path,
    mark_document_served,
    try_mark_document_downloaded,
)
from src.notifications import notify_recipient_of_document, notify_sender_of_download
from src.pdf_generator import (
    generate_proof_of_service,
    generate_stamped_pdf,
    get_proof_of_service_filename,
    get_stamped_pdf_filename,
)


router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# =============================================================================
# UPLOAD
# =============================================================================

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Display the document upload page."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/upload", status_code=303)

    # Check if OCR is enabled
    ocr_enabled = getattr(settings, 'OCR_ENABLED', False)

    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
            "ocr_enabled": ocr_enabled,
        }
    )


@router.post("/upload/extract", response_class=HTMLResponse)
async def extract_document_details(
    request: Request,
    document: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract details from uploaded PDF and return form field suggestions via HTMX.

    This endpoint is called when the user clicks "Extract Details" button.
    It uses OCR to extract recipient, matter reference, and description from the PDF.
    """
    user = await get_current_user(request, db)
    if not user:
        return HTMLResponse(
            '<div class="text-red-600 text-sm">Please log in to use this feature.</div>',
            status_code=401
        )

    # Check if OCR is enabled
    if not getattr(settings, 'OCR_ENABLED', False):
        return HTMLResponse(
            '<div class="text-yellow-600 text-sm">OCR extraction is not enabled.</div>',
            status_code=400
        )

    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            content = await document.read()
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)

        try:
            # Run OCR extraction
            from src.ocr_processor import extract_for_upload_form
            extraction = await extract_for_upload_form(tmp_path)

            # Build HTML response with extracted data
            confidence = extraction.get("confidence", 0)
            confidence_class = "text-green-600" if confidence > 0.7 else "text-yellow-600" if confidence > 0.4 else "text-red-600"

            html_parts = [
                f'<div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">',
                f'<div class="flex items-center justify-between mb-2">',
                f'<span class="text-green-800 font-medium">Details Extracted</span>',
                f'<span class="{confidence_class} text-sm">Confidence: {confidence * 100:.0f}%</span>',
                f'</div>',
            ]

            # Show what was extracted
            if extraction.get("recipient_email"):
                html_parts.append(f'<div class="text-sm text-green-700">Recipient: {extraction["recipient_email"]}</div>')
            if extraction.get("matter_reference"):
                html_parts.append(f'<div class="text-sm text-green-700">Matter: {extraction["matter_reference"]}</div>')

            html_parts.append('</div>')

            # JavaScript to fill form fields
            html_parts.append('<script>')
            if extraction.get("recipient_email"):
                html_parts.append(f'document.getElementById("recipient_email").value = "{extraction["recipient_email"]}";')
            if extraction.get("recipient_name"):
                html_parts.append(f'document.getElementById("recipient_name").value = "{extraction["recipient_name"]}";')
            if extraction.get("matter_reference"):
                html_parts.append(f'document.getElementById("matter_reference").value = "{extraction["matter_reference"]}";')
            if extraction.get("description"):
                # Escape quotes in description
                desc = extraction["description"].replace('"', '\\"').replace('\n', ' ')
                html_parts.append(f'document.getElementById("description").value = "{desc}";')
            html_parts.append('</script>')

            return HTMLResponse("".join(html_parts))

        finally:
            # Clean up temp file
            os.unlink(tmp_path)

    except Exception as e:
        return HTMLResponse(
            f'<div class="text-red-600 text-sm">Extraction failed: {str(e)}</div>',
            status_code=500
        )


@router.post("/upload")
async def upload_submit(
    request: Request,
    recipient_email: str = Form(...),
    recipient_name: str = Form(None),
    matter_reference: str = Form(None),
    description: str = Form(None),
    document: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Process document upload."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/upload", status_code=303)

    try:
        # Create document record and save file
        doc = await create_document(
            db=db,
            file=document,
            sender=user,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            matter_reference=matter_reference,
            description=description,
        )

        # Check if AES signing is required before serving
        if settings.AES_REQUIRED_FOR_SERVICE:
            # Document needs to be signed first - redirect to signing page
            return RedirectResponse(
                url=f"/signing/document/{doc.id}",
                status_code=303
            )

        # AES not required - serve immediately
        # Generate download URL and send notification to recipient
        # Per ECTA Section 23: Attach the actual PDF so it enters recipient's information system
        download_url = f"{settings.BASE_URL}/download/{doc.download_token}"
        pdf_path = get_file_path(doc.stored_filename)
        notification_sent, message_id = await notify_recipient_of_document(doc, download_url, pdf_path)

        # Mark document as served and store email tracking info
        if notification_sent:
            if message_id:
                doc.email_message_id = message_id
                doc.email_status = "sent"
            await mark_document_served(db, doc)

        # Redirect to success page
        return RedirectResponse(
            url=f"/upload/success/{doc.id}",
            status_code=303
        )

    except HTTPException as e:
        # Re-render form with error
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": user,
                "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
                "error": e.detail,
                "recipient_email": recipient_email,
                "recipient_name": recipient_name,
                "matter_reference": matter_reference,
                "description": description,
            },
            status_code=400,
        )


@router.get("/upload/success/{document_id}", response_class=HTMLResponse)
async def upload_success(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Display upload success page with document details."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    doc = await get_document_by_id(db, document_id)
    if not doc or doc.sender_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Generate download URL
    download_url = f"{settings.BASE_URL}/download/{doc.download_token}"

    return templates.TemplateResponse(
        "upload_success.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "document": doc,
            "download_url": download_url,
        }
    )


# =============================================================================
# DOWNLOAD
# =============================================================================

@router.get("/download/{token}", response_class=HTMLResponse)
async def download_page(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Display the download page for a document."""
    doc = await get_document_by_token(db, token)

    if not doc:
        return templates.TemplateResponse(
            "download_error.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "error": "Document not found",
                "message": "This download link is invalid or the document has been removed.",
            },
            status_code=404,
        )

    if doc.is_expired:
        return templates.TemplateResponse(
            "download_error.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "error": "Link expired",
                "message": "This download link has expired. Please contact the sender for a new link.",
            },
            status_code=410,
        )

    return templates.TemplateResponse(
        "download.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "document": doc,
            "already_downloaded": doc.is_downloaded,
        }
    )


@router.post("/download/{token}")
async def download_file(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Download the document file."""
    doc = await get_document_by_token(db, token)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.is_expired:
        raise HTTPException(status_code=410, detail="Download link expired")

    # Get file path
    file_path = get_file_path(doc.stored_filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")

    # Atomically mark as downloaded if first time, then notify sender
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    rows_affected = await try_mark_document_downloaded(db, doc, client_ip, user_agent)

    if rows_affected > 0:
        # First download - notify sender
        await notify_sender_of_download(doc)

    # Return the file
    return FileResponse(
        path=file_path,
        filename=doc.original_filename,
        media_type="application/pdf",
    )


# =============================================================================
# DOCUMENT LIST
# =============================================================================

@router.get("/documents", response_class=HTMLResponse)
async def documents_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List documents sent by the user."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/documents", status_code=303)

    documents = await get_user_sent_documents(db, user.id)

    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "documents": documents,
        }
    )


@router.get("/document/{document_id}", response_class=HTMLResponse)
async def document_detail(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """View details of a specific document."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    doc = await get_document_by_id(db, document_id)
    if not doc or doc.sender_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    download_url = f"{settings.BASE_URL}/download/{doc.download_token}"

    return templates.TemplateResponse(
        "document_detail.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "document": doc,
            "download_url": download_url,
        }
    )


# =============================================================================
# SERVE DOCUMENT (after signing)
# =============================================================================

@router.post("/document/{document_id}/serve")
async def serve_document(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Serve the document to the recipient (after AES signing).

    This sends the notification email with the PDF attached and marks
    the document as served per ECTA Section 23.
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    doc = await get_document_by_id(db, document_id)
    if not doc or doc.sender_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if already served
    if doc.is_served:
        return RedirectResponse(
            url=f"/document/{document_id}?already_served=true",
            status_code=303
        )

    # Check if AES signing is required and document is not signed
    if settings.AES_REQUIRED_FOR_SERVICE and not doc.is_signed:
        return RedirectResponse(
            url=f"/signing/document/{document_id}?error=Please+sign+before+serving",
            status_code=303
        )

    # Generate download URL and send notification to recipient
    # Per ECTA Section 23: Attach the actual PDF so it enters recipient's information system
    download_url = f"{settings.BASE_URL}/download/{doc.download_token}"
    pdf_path = get_file_path(doc.stored_filename)
    notification_sent, message_id = await notify_recipient_of_document(doc, download_url, pdf_path)

    # Mark document as served and store email tracking info
    if notification_sent:
        # Store message ID for email tracking
        if message_id:
            doc.email_message_id = message_id
            doc.email_status = "sent"

        await mark_document_served(db, doc)
        return RedirectResponse(
            url=f"/document/{document_id}?served=true",
            status_code=303
        )
    else:
        return RedirectResponse(
            url=f"/document/{document_id}?error=Failed+to+send+notification",
            status_code=303
        )


# =============================================================================
# PROOF OF SERVICE & STAMPED PDF
# =============================================================================

@router.get("/document/{document_id}/proof-of-service")
async def download_proof_of_service(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download the Proof of Service PDF for a document."""
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    doc = await get_document_by_id(db, document_id)
    if not doc or doc.sender_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Generate Proof of Service PDF
    pdf_bytes = generate_proof_of_service(doc)
    filename = get_proof_of_service_filename(doc)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/document/{document_id}/stamped")
async def download_stamped_pdf(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download the stamped PDF (original document with service confirmation stamp)."""
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    doc = await get_document_by_id(db, document_id)
    if not doc or doc.sender_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if document has been served (per ECTA Section 23)
    if not doc.is_served:
        raise HTTPException(
            status_code=400,
            detail="Stamped PDF is only available after the document has been served"
        )

    # Get original file path
    original_path = get_file_path(doc.stored_filename)
    if not original_path.exists():
        raise HTTPException(status_code=404, detail="Original file not found")

    # Generate stamped PDF
    pdf_bytes = generate_stamped_pdf(doc, original_path)
    filename = get_stamped_pdf_filename(doc)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

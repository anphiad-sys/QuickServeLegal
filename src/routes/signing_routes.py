"""
QuickServe Legal - Signing Routes

Handles the AES document signing workflow.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, TEMPLATES_DIR
from src.database import get_db
from src.auth import get_current_user
from src.documents import get_document_by_id, get_file_path
from src.signatures import (
    sign_document,
    get_user_active_certificate,
    compute_document_hash,
    get_document_signature,
)
from src.certificate_manager import can_user_sign
from src.audit import log_event
from src.models.audit import AuditEventType
from src.pdf_generator import (
    generate_court_filing_certificate,
    get_court_filing_certificate_filename,
    append_wet_ink_placeholder,
    get_placeholder_filename,
)


router = APIRouter(prefix="/signing", tags=["signing"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/document/{document_id}", response_class=HTMLResponse)
async def signing_page(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Display the document signing page."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"/login?next=/signing/document/{document_id}", status_code=303)

    # Get document
    document = await get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify ownership
    if document.sender_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if already signed
    if document.is_signed:
        return RedirectResponse(url=f"/document/{document_id}", status_code=303)

    # Check signing eligibility
    signing_check = await can_user_sign(db, user)

    # Get active certificate if available
    certificate = signing_check.get("certificate")

    # Compute document hash if not already done
    if not document.document_hash:
        file_path = get_file_path(document.stored_filename)
        document.document_hash = compute_document_hash(file_path)
        await db.commit()

    return templates.TemplateResponse(
        "signing.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "document": document,
            "can_sign": signing_check["can_sign"],
            "signing_reason": signing_check.get("reason"),
            "signing_warning": signing_check.get("warning"),
            "certificate": certificate,
            "mock_mode": settings.LAWTRUST_MOCK_MODE,
        }
    )


@router.post("/document/{document_id}")
async def sign_document_submit(
    request: Request,
    document_id: int,
    confirm_sign: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Process document signing."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"/login?next=/signing/document/{document_id}", status_code=303)

    # Get document
    document = await get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify ownership
    if document.sender_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if already signed
    if document.is_signed:
        return RedirectResponse(url=f"/document/{document_id}", status_code=303)

    # Verify confirmation
    if confirm_sign != "yes":
        return RedirectResponse(
            url=f"/signing/document/{document_id}?error=Please+confirm+signing",
            status_code=303
        )

    # Get certificate
    certificate = await get_user_active_certificate(db, user.id)
    if not certificate:
        return RedirectResponse(
            url=f"/signing/document/{document_id}?error=No+valid+certificate+found",
            status_code=303
        )

    # Get client IP
    client_ip = request.client.host if request.client else None

    try:
        # Append wet-ink placeholder page to document
        original_path = get_file_path(document.stored_filename)
        placeholder_filename = get_placeholder_filename(document)
        placeholder_path = settings.UPLOAD_DIR / placeholder_filename.replace(" ", "_")

        append_wet_ink_placeholder(original_path, placeholder_path)
        document.with_placeholder_filename = placeholder_path.name

        # Log placeholder addition
        await log_event(
            db=db,
            event_type=AuditEventType.SIGNATURE_PLACEHOLDER_ADDED,
            description=f"Wet-ink placeholder page added to document '{document.original_filename}'",
            user_id=user.id,
            document_id=document.id,
            ip_address=client_ip,
        )

        # Sign the document
        signature, document = await sign_document(
            db=db,
            document=document,
            user=user,
            certificate=certificate,
            ip_address=client_ip,
        )

        # Redirect to document detail page
        return RedirectResponse(
            url=f"/document/{document_id}?signed=true",
            status_code=303
        )

    except ValueError as e:
        return RedirectResponse(
            url=f"/signing/document/{document_id}?error={str(e)}",
            status_code=303
        )
    except Exception as e:
        # Log unexpected error
        await log_event(
            db=db,
            event_type=AuditEventType.SIGNATURE_FAILED,
            description=f"Signing failed with unexpected error: {str(e)}",
            user_id=user.id,
            document_id=document.id,
            ip_address=client_ip,
        )
        return RedirectResponse(
            url=f"/signing/document/{document_id}?error=Signing+failed.+Please+try+again.",
            status_code=303
        )


@router.get("/document/{document_id}/court-certificate")
async def download_court_certificate(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download the Court Filing Certificate for a signed document."""
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get document
    document = await get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify ownership
    if document.sender_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if signed
    if not document.is_signed:
        raise HTTPException(status_code=400, detail="Document must be signed to generate Court Filing Certificate")

    # Get signature and certificate
    signature = await get_document_signature(db, document.id)
    if not signature:
        raise HTTPException(status_code=404, detail="Signature not found")

    # Get certificate
    from src.certificate_manager import get_certificate_by_id
    certificate = await get_certificate_by_id(db, signature.certificate_id)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    # Log generation
    client_ip = request.client.host if request.client else None
    await log_event(
        db=db,
        event_type=AuditEventType.COURT_CERTIFICATE_GENERATED,
        description=f"Court Filing Certificate generated for document '{document.original_filename}'",
        user_id=user.id,
        document_id=document.id,
        ip_address=client_ip,
    )

    # Generate PDF
    pdf_bytes = generate_court_filing_certificate(document, signature, certificate)
    filename = get_court_filing_certificate_filename(document)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

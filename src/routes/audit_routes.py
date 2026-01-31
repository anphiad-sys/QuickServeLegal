"""
QuickServe Legal - Audit Trail Routes

Provides viewing and export of audit logs for documents.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, TEMPLATES_DIR
from src.database import get_db
from src.auth import get_current_user
from src.documents import get_document_by_id
from src.audit import (
    get_document_audit_trail,
    verify_audit_chain_integrity,
    export_audit_trail_to_json,
)


router = APIRouter(prefix="/audit", tags=["audit"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/document/{document_id}", response_class=HTMLResponse)
async def audit_trail_page(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Display the audit trail for a document."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"/login?next=/audit/document/{document_id}", status_code=303)

    # Get document
    document = await get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify ownership
    if document.sender_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get audit trail
    audit_entries = await get_document_audit_trail(db, document_id)

    # Verify chain integrity
    integrity_check = await verify_audit_chain_integrity(db)

    return templates.TemplateResponse(
        "audit_trail.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "document": document,
            "audit_entries": audit_entries,
            "integrity_valid": integrity_check["valid"],
            "integrity_error": integrity_check.get("error"),
        }
    )


@router.get("/document/{document_id}/export")
async def export_audit_trail(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Export the audit trail for a document as JSON."""
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

    # Get audit trail
    audit_entries = await get_document_audit_trail(db, document_id)

    # Export to JSON
    json_content = export_audit_trail_to_json(audit_entries)
    filename = f"AuditTrail_QSL-{document_id:06d}.json"

    return Response(
        content=json_content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/verify", response_class=HTMLResponse)
async def verify_integrity_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Page to verify overall audit log integrity (admin feature)."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/audit/verify", status_code=303)

    # Verify entire chain
    integrity_check = await verify_audit_chain_integrity(db)

    return templates.TemplateResponse(
        "audit_verify.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "integrity_check": integrity_check,
        }
    )


# Import RedirectResponse for the missing import
from fastapi.responses import RedirectResponse

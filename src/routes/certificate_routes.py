"""
QuickServe Legal - Certificate Management Routes

Handles certificate listing, registration, and management.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, TEMPLATES_DIR
from src.database import get_db
from src.auth import get_current_user
from src.certificate_manager import (
    get_user_certificates,
    get_certificate_by_id,
    check_certificate_status,
    deactivate_certificate,
    reactivate_certificate,
)
from src.signatures import create_mock_certificate
from src.audit import log_event
from src.models.audit import AuditEventType


router = APIRouter(prefix="/certificates", tags=["certificates"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("", response_class=HTMLResponse)
async def certificates_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Display the user's certificates."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/certificates", status_code=303)

    # Get all certificates (including inactive for display)
    certificates = await get_user_certificates(db, user.id, include_inactive=True)

    # Get status details for each certificate
    cert_details = [check_certificate_status(cert) for cert in certificates]

    # Check for any valid certificate
    has_valid = any(cert.is_valid for cert in certificates)

    return templates.TemplateResponse(
        "certificates.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "certificates": certificates,
            "cert_details": cert_details,
            "has_valid_certificate": has_valid,
            "mock_mode": settings.LAWTRUST_MOCK_MODE,
            "success_message": request.query_params.get("success"),
            "error_message": request.query_params.get("error"),
        }
    )


@router.post("/register-mock")
async def register_mock_certificate(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a mock certificate for testing (only in mock mode).
    """
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/certificates", status_code=303)

    # Only allow in mock mode
    if not settings.LAWTRUST_MOCK_MODE:
        return RedirectResponse(
            url="/certificates?error=Mock+certificates+not+allowed+in+production+mode",
            status_code=303
        )

    # Check if user is verified (attorneys only can sign)
    if not user.is_verified:
        return RedirectResponse(
            url="/certificates?error=Only+verified+attorneys+can+register+certificates",
            status_code=303
        )

    try:
        # Create mock certificate
        certificate = await create_mock_certificate(db, user)

        # Log the event
        client_ip = request.client.host if request.client else None
        await log_event(
            db=db,
            event_type=AuditEventType.CERTIFICATE_REGISTERED,
            description=f"Mock certificate registered: {certificate.certificate_serial}",
            user_id=user.id,
            metadata={
                "certificate_id": certificate.id,
                "certificate_serial": certificate.certificate_serial,
                "is_mock": True,
            },
            ip_address=client_ip,
        )

        return RedirectResponse(
            url="/certificates?success=Mock+certificate+registered+successfully",
            status_code=303
        )

    except Exception as e:
        return RedirectResponse(
            url=f"/certificates?error=Failed+to+register+certificate:+{str(e)}",
            status_code=303
        )


@router.post("/{certificate_id}/deactivate")
async def deactivate_certificate_route(
    request: Request,
    certificate_id: int,
    reason: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a certificate."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/certificates", status_code=303)

    # Get certificate
    certificate = await get_certificate_by_id(db, certificate_id)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    # Verify ownership
    if certificate.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if already inactive
    if not certificate.is_active:
        return RedirectResponse(
            url="/certificates?error=Certificate+is+already+inactive",
            status_code=303
        )

    # Get client IP
    client_ip = request.client.host if request.client else None

    # Deactivate
    await deactivate_certificate(
        db=db,
        certificate=certificate,
        user_id=user.id,
        reason=reason,
        ip_address=client_ip,
    )

    return RedirectResponse(
        url="/certificates?success=Certificate+deactivated+successfully",
        status_code=303
    )


@router.post("/{certificate_id}/reactivate")
async def reactivate_certificate_route(
    request: Request,
    certificate_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Reactivate a previously deactivated certificate."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/certificates", status_code=303)

    # Get certificate
    certificate = await get_certificate_by_id(db, certificate_id)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    # Verify ownership
    if certificate.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get client IP
    client_ip = request.client.host if request.client else None

    try:
        await reactivate_certificate(
            db=db,
            certificate=certificate,
            user_id=user.id,
            ip_address=client_ip,
        )

        return RedirectResponse(
            url="/certificates?success=Certificate+reactivated+successfully",
            status_code=303
        )

    except ValueError as e:
        return RedirectResponse(
            url=f"/certificates?error={str(e)}",
            status_code=303
        )


@router.get("/{certificate_id}", response_class=HTMLResponse)
async def certificate_detail(
    request: Request,
    certificate_id: int,
    db: AsyncSession = Depends(get_db),
):
    """View certificate details."""
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Get certificate
    certificate = await get_certificate_by_id(db, certificate_id)
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    # Verify ownership
    if certificate.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get detailed status
    status = check_certificate_status(certificate)

    return templates.TemplateResponse(
        "certificate_detail.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "certificate": certificate,
            "status": status,
        }
    )

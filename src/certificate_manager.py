"""
QuickServe Legal - Certificate Manager

Manages LAWTrust digital certificates for attorneys.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.certificate import Certificate
from src.models.user import User
from src.models.audit import AuditEventType
from src.audit import log_event


async def get_user_certificates(
    db: AsyncSession,
    user_id: int,
    include_inactive: bool = False,
) -> List[Certificate]:
    """
    Get all certificates for a user.

    Args:
        db: Database session
        user_id: User ID
        include_inactive: Whether to include inactive/revoked certificates

    Returns:
        List of Certificate objects
    """
    query = select(Certificate).where(Certificate.user_id == user_id)

    if not include_inactive:
        query = query.where(
            Certificate.is_active == True,
            Certificate.revoked_at.is_(None),
        )

    query = query.order_by(Certificate.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_certificate_by_id(
    db: AsyncSession,
    certificate_id: int,
) -> Optional[Certificate]:
    """Get a certificate by its ID."""
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id)
    )
    return result.scalar_one_or_none()


async def get_certificate_by_serial(
    db: AsyncSession,
    serial: str,
) -> Optional[Certificate]:
    """Get a certificate by its serial number."""
    result = await db.execute(
        select(Certificate).where(Certificate.certificate_serial == serial)
    )
    return result.scalar_one_or_none()


def check_certificate_status(certificate: Certificate) -> dict:
    """
    Get detailed status information for a certificate.

    Args:
        certificate: Certificate to check

    Returns:
        Dictionary with status details
    """
    now = datetime.utcnow()

    return {
        "certificate_id": certificate.id,
        "serial": certificate.certificate_serial,
        "subject": certificate.subject,
        "common_name": certificate.common_name,
        "is_valid": certificate.is_valid,
        "is_expired": certificate.is_expired,
        "is_revoked": certificate.is_revoked,
        "is_active": certificate.is_active,
        "is_mock": certificate.is_mock,
        "status_text": certificate.status_text,
        "days_until_expiry": certificate.days_until_expiry,
        "valid_from": certificate.valid_from.isoformat(),
        "valid_until": certificate.valid_until.isoformat(),
        "revoked_at": certificate.revoked_at.isoformat() if certificate.revoked_at else None,
        "revocation_reason": certificate.revocation_reason,
    }


async def can_user_sign(db: AsyncSession, user: User) -> dict:
    """
    Check if a user can sign documents.

    Args:
        db: Database session
        user: User to check

    Returns:
        Dictionary with signing eligibility details
    """
    # Check if user is verified
    if not user.is_verified:
        return {
            "can_sign": False,
            "reason": "User is not verified as an attorney",
            "certificate": None,
        }

    # Get active certificate
    certificates = await get_user_certificates(db, user.id, include_inactive=False)
    valid_cert = None

    for cert in certificates:
        if cert.is_valid:
            valid_cert = cert
            break

    if not valid_cert:
        return {
            "can_sign": False,
            "reason": "No valid certificate found",
            "certificate": None,
        }

    # Check certificate expiry warning
    warning = None
    if valid_cert.days_until_expiry <= 30:
        warning = f"Certificate expires in {valid_cert.days_until_expiry} days"

    return {
        "can_sign": True,
        "reason": None,
        "certificate": valid_cert,
        "warning": warning,
    }


async def deactivate_certificate(
    db: AsyncSession,
    certificate: Certificate,
    user_id: int,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Certificate:
    """
    Deactivate a certificate (soft disable, not revocation).

    Args:
        db: Database session
        certificate: Certificate to deactivate
        user_id: User performing the action
        reason: Optional reason for deactivation
        ip_address: Optional client IP

    Returns:
        Updated Certificate
    """
    certificate.is_active = False

    await db.commit()
    await db.refresh(certificate)

    # Log the event
    await log_event(
        db=db,
        event_type=AuditEventType.CERTIFICATE_DEACTIVATED,
        description=f"Certificate {certificate.certificate_serial} deactivated" + (f": {reason}" if reason else ""),
        user_id=user_id,
        metadata={
            "certificate_id": certificate.id,
            "certificate_serial": certificate.certificate_serial,
            "reason": reason,
        },
        ip_address=ip_address,
    )

    return certificate


async def reactivate_certificate(
    db: AsyncSession,
    certificate: Certificate,
    user_id: int,
    ip_address: Optional[str] = None,
) -> Certificate:
    """
    Reactivate a previously deactivated certificate.

    Args:
        db: Database session
        certificate: Certificate to reactivate
        user_id: User performing the action
        ip_address: Optional client IP

    Returns:
        Updated Certificate

    Raises:
        ValueError: If certificate is revoked or expired
    """
    if certificate.is_revoked:
        raise ValueError("Cannot reactivate a revoked certificate")

    if certificate.is_expired:
        raise ValueError("Cannot reactivate an expired certificate")

    certificate.is_active = True

    await db.commit()
    await db.refresh(certificate)

    # Log the event
    await log_event(
        db=db,
        event_type=AuditEventType.CERTIFICATE_ACTIVATED,
        description=f"Certificate {certificate.certificate_serial} reactivated",
        user_id=user_id,
        metadata={
            "certificate_id": certificate.id,
            "certificate_serial": certificate.certificate_serial,
        },
        ip_address=ip_address,
    )

    return certificate


async def revoke_certificate(
    db: AsyncSession,
    certificate: Certificate,
    user_id: int,
    reason: str,
    ip_address: Optional[str] = None,
) -> Certificate:
    """
    Revoke a certificate (permanent, cannot be undone).

    Args:
        db: Database session
        certificate: Certificate to revoke
        user_id: User performing the action
        reason: Reason for revocation (required)
        ip_address: Optional client IP

    Returns:
        Updated Certificate
    """
    certificate.is_active = False
    certificate.revoked_at = datetime.utcnow()
    certificate.revocation_reason = reason

    await db.commit()
    await db.refresh(certificate)

    # Log the event
    await log_event(
        db=db,
        event_type=AuditEventType.CERTIFICATE_REVOKED,
        description=f"Certificate {certificate.certificate_serial} revoked: {reason}",
        user_id=user_id,
        metadata={
            "certificate_id": certificate.id,
            "certificate_serial": certificate.certificate_serial,
            "reason": reason,
        },
        ip_address=ip_address,
    )

    return certificate


async def check_expiring_certificates(
    db: AsyncSession,
    days_threshold: int = 30,
) -> List[Certificate]:
    """
    Find certificates that will expire within the given threshold.

    Args:
        db: Database session
        days_threshold: Number of days to look ahead

    Returns:
        List of soon-to-expire Certificate objects
    """
    from datetime import timedelta

    threshold_date = datetime.utcnow() + timedelta(days=days_threshold)

    result = await db.execute(
        select(Certificate)
        .where(
            Certificate.is_active == True,
            Certificate.revoked_at.is_(None),
            Certificate.valid_until <= threshold_date,
            Certificate.valid_until > datetime.utcnow(),  # Not already expired
        )
        .order_by(Certificate.valid_until.asc())
    )

    return list(result.scalars().all())

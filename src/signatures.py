"""
QuickServe Legal - Signature Service

Handles document signing with LAWTrust AES integration.
In development mode, uses a mock API for testing.
"""

import hashlib
import base64
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.document import Document
from src.models.certificate import Certificate
from src.models.signature import Signature
from src.models.user import User
from src.models.audit import AuditEventType
from src.audit import log_signing_event


def compute_document_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a PDF document.

    Args:
        file_path: Path to the PDF file

    Returns:
        Hexadecimal hash string
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks for memory efficiency with large files
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class MockLAWTrustAPI:
    """
    Mock LAWTrust API for development and testing.

    Simulates the LAWTrust AES signing process without
    actually calling the LAWTrust service.
    """

    @staticmethod
    def generate_mock_signature(document_hash: str, certificate: Certificate) -> dict:
        """
        Generate a mock digital signature.

        Args:
            document_hash: SHA-256 hash of the document
            certificate: The certificate to "sign" with

        Returns:
            Dictionary with signature data
        """
        # Create a deterministic but unique signature value
        signature_data = f"{document_hash}:{certificate.certificate_serial}:{datetime.utcnow().isoformat()}"
        signature_bytes = hashlib.sha512(signature_data.encode()).digest()
        signature_value = base64.b64encode(signature_bytes).decode()

        # Generate a mock LAWTrust reference
        lawtrust_ref = f"MOCK-LT-{uuid.uuid4().hex[:16].upper()}"

        return {
            "signature_value": signature_value,
            "lawtrust_reference": lawtrust_ref,
            "lawtrust_timestamp": datetime.utcnow().isoformat(),
            "signing_method": "MOCK",
            "signature_algorithm": "SHA256withRSA",
            "success": True,
            "error": None,
        }

    @staticmethod
    def verify_mock_signature(signature: Signature) -> dict:
        """
        Verify a mock signature (always returns valid for mock sigs).
        """
        return {
            "valid": True,
            "signer": "Mock Signer",
            "signed_at": signature.signed_at.isoformat(),
            "certificate_serial": "MOCK-CERT",
        }


class LAWTrustAPI:
    """
    LAWTrust API client for production AES signing.

    This is a placeholder for the real LAWTrust integration.
    Actual implementation requires LAWTrust partner documentation.
    """

    def __init__(self, api_url: str, api_key: str, api_secret: str):
        self.api_url = api_url
        self.api_key = api_key
        self.api_secret = api_secret

    async def sign_document(
        self,
        document_hash: str,
        certificate_serial: str,
        user_id: str,
    ) -> dict:
        """
        Sign a document using LAWTrust AES.

        This is a placeholder. Real implementation would:
        1. Authenticate with LAWTrust API
        2. Send document hash for signing
        3. Receive signature and timestamp
        4. Return signature data

        Args:
            document_hash: SHA-256 hash of the document
            certificate_serial: Serial number of the signing certificate
            user_id: User identifier for LAWTrust

        Returns:
            Dictionary with signature data
        """
        # Placeholder - raise error to indicate real implementation needed
        raise NotImplementedError(
            "LAWTrust API integration not implemented. "
            "Set LAWTRUST_MOCK_MODE=True for development."
        )

    async def verify_signature(self, signature_value: str, document_hash: str) -> dict:
        """
        Verify a signature with LAWTrust.

        Placeholder for real implementation.
        """
        raise NotImplementedError("LAWTrust API integration not implemented.")


async def get_user_active_certificate(
    db: AsyncSession,
    user_id: int,
) -> Optional[Certificate]:
    """
    Get the active, valid certificate for a user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        Certificate if found and valid, None otherwise
    """
    result = await db.execute(
        select(Certificate)
        .where(
            Certificate.user_id == user_id,
            Certificate.is_active == True,
            Certificate.revoked_at.is_(None),
        )
        .order_by(Certificate.valid_until.desc())
    )
    certificates = list(result.scalars().all())

    # Return the first valid certificate
    for cert in certificates:
        if cert.is_valid:
            return cert

    return None


async def register_certificate(
    db: AsyncSession,
    user_id: int,
    certificate_serial: str,
    subject: str,
    issuer: str,
    valid_from: datetime,
    valid_until: datetime,
    certificate_data: Optional[str] = None,
    is_mock: bool = False,
) -> Certificate:
    """
    Register a new certificate for a user.

    Args:
        db: Database session
        user_id: User ID
        certificate_serial: Unique serial number
        subject: Certificate subject (DN)
        issuer: Certificate issuer (CA DN)
        valid_from: Start of validity period
        valid_until: End of validity period
        certificate_data: Optional base64-encoded certificate
        is_mock: Whether this is a mock certificate

    Returns:
        The created Certificate
    """
    certificate = Certificate(
        user_id=user_id,
        certificate_serial=certificate_serial,
        subject=subject,
        issuer=issuer,
        valid_from=valid_from,
        valid_until=valid_until,
        certificate_data=certificate_data,
        is_mock=is_mock,
        is_active=True,
    )

    db.add(certificate)
    await db.commit()
    await db.refresh(certificate)

    return certificate


async def create_mock_certificate(
    db: AsyncSession,
    user: User,
) -> Certificate:
    """
    Create a mock certificate for testing.

    Args:
        db: Database session
        user: User to create certificate for

    Returns:
        The created mock Certificate
    """
    serial = f"MOCK-{uuid.uuid4().hex[:16].upper()}"
    subject = f"CN={user.full_name}, O={user.firm_name or 'Law Firm'}, C=ZA"
    issuer = "CN=Mock LAWTrust CA, O=Mock Certification Authority, C=ZA"

    valid_from = datetime.utcnow()
    valid_until = valid_from + timedelta(days=settings.AES_CERTIFICATE_VALIDITY_DAYS)

    return await register_certificate(
        db=db,
        user_id=user.id,
        certificate_serial=serial,
        subject=subject,
        issuer=issuer,
        valid_from=valid_from,
        valid_until=valid_until,
        is_mock=True,
    )


async def sign_document(
    db: AsyncSession,
    document: Document,
    user: User,
    certificate: Certificate,
    ip_address: Optional[str] = None,
) -> Tuple[Signature, Document]:
    """
    Sign a document with AES.

    Args:
        db: Database session
        document: Document to sign
        user: Signing user
        certificate: Certificate to use for signing
        ip_address: Optional client IP address

    Returns:
        Tuple of (Signature, updated Document)

    Raises:
        ValueError: If certificate is not valid or document already signed
    """
    # Validate certificate
    if not certificate.is_valid:
        raise ValueError(f"Certificate is not valid: {certificate.status_text}")

    if certificate.user_id != user.id:
        raise ValueError("Certificate does not belong to this user")

    # Validate document
    if document.is_signed:
        raise ValueError("Document is already signed")

    # Get document hash (compute if not already stored)
    if not document.document_hash:
        file_path = settings.UPLOAD_DIR / document.stored_filename
        document.document_hash = compute_document_hash(file_path)

    # Log signing request
    await log_signing_event(
        db=db,
        event_type=AuditEventType.SIGNATURE_REQUESTED,
        document_id=document.id,
        user_id=user.id,
        certificate_id=certificate.id,
        description=f"Signature requested for document '{document.original_filename}'",
        ip_address=ip_address,
    )

    # Perform signing (mock or real)
    if settings.LAWTRUST_MOCK_MODE or certificate.is_mock:
        # Use mock signing
        sign_result = MockLAWTrustAPI.generate_mock_signature(
            document_hash=document.document_hash,
            certificate=certificate,
        )
    else:
        # Use real LAWTrust API
        api = LAWTrustAPI(
            api_url=settings.LAWTRUST_API_URL,
            api_key=settings.LAWTRUST_API_KEY,
            api_secret=settings.LAWTRUST_API_SECRET,
        )
        sign_result = await api.sign_document(
            document_hash=document.document_hash,
            certificate_serial=certificate.certificate_serial,
            user_id=str(user.id),
        )

    if not sign_result.get("success", False):
        # Log failure
        await log_signing_event(
            db=db,
            event_type=AuditEventType.SIGNATURE_FAILED,
            document_id=document.id,
            user_id=user.id,
            certificate_id=certificate.id,
            description=f"Signing failed: {sign_result.get('error', 'Unknown error')}",
            ip_address=ip_address,
        )
        raise ValueError(f"Signing failed: {sign_result.get('error', 'Unknown error')}")

    # Create signature record
    signature = Signature(
        document_id=document.id,
        signer_user_id=user.id,
        certificate_id=certificate.id,
        signed_hash=document.document_hash,
        signature_value=sign_result["signature_value"],
        lawtrust_reference=sign_result.get("lawtrust_reference"),
        lawtrust_timestamp=sign_result.get("lawtrust_timestamp"),
        signing_method=sign_result.get("signing_method", "AES"),
        signature_algorithm=sign_result.get("signature_algorithm", "SHA256withRSA"),
        signed_at=datetime.utcnow(),
    )

    db.add(signature)
    await db.flush()  # Get the signature ID

    # Update document
    document.signing_status = "signed"
    document.signed_at = datetime.utcnow()
    document.signed_by_user_id = user.id
    document.signature_id = signature.id

    await db.commit()
    await db.refresh(document)
    await db.refresh(signature)

    # Log success
    await log_signing_event(
        db=db,
        event_type=AuditEventType.SIGNATURE_COMPLETED,
        document_id=document.id,
        user_id=user.id,
        certificate_id=certificate.id,
        signature_id=signature.id,
        description=f"Document '{document.original_filename}' signed successfully with certificate {certificate.certificate_serial}",
        ip_address=ip_address,
    )

    return signature, document


async def get_signature_by_id(db: AsyncSession, signature_id: int) -> Optional[Signature]:
    """Get a signature by its ID."""
    result = await db.execute(
        select(Signature).where(Signature.id == signature_id)
    )
    return result.scalar_one_or_none()


async def get_document_signature(db: AsyncSession, document_id: int) -> Optional[Signature]:
    """Get the signature for a document."""
    result = await db.execute(
        select(Signature).where(Signature.document_id == document_id)
    )
    return result.scalar_one_or_none()

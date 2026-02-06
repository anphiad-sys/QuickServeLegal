"""
QuickServe Legal - Certificate Model

Stores LAWTrust digital certificate information for attorneys.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.timestamps import now_utc


class Certificate(Base):
    """
    Digital certificate for an attorney, used for AES signing.

    In production, certificates are issued by LAWTrust.
    In development, mock certificates can be created for testing.
    """

    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Owner
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Certificate details (from LAWTrust)
    certificate_serial: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)  # Distinguished Name
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)  # CA Distinguished Name

    # Validity period
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Certificate data (optional - may store base64-encoded public cert)
    certificate_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Fingerprints for verification
    thumbprint_sha1: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    thumbprint_sha256: Mapped[Optional[str]] = mapped_column(String(70), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)  # True for dev/test certs
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Certificate {self.certificate_serial} for user {self.user_id}>"

    @property
    def is_valid(self) -> bool:
        """Check if certificate is currently valid."""
        now = now_utc()
        return (
            self.is_active
            and self.revoked_at is None
            and self.valid_from <= now <= self.valid_until
        )

    @property
    def is_expired(self) -> bool:
        """Check if certificate has expired."""
        return now_utc() > self.valid_until

    @property
    def is_revoked(self) -> bool:
        """Check if certificate has been revoked."""
        return self.revoked_at is not None

    @property
    def days_until_expiry(self) -> int:
        """Get number of days until certificate expires."""
        if self.is_expired:
            return 0
        delta = self.valid_until - now_utc()
        return max(0, delta.days)

    @property
    def status_text(self) -> str:
        """Get human-readable status."""
        if self.is_revoked:
            return "Revoked"
        if self.is_expired:
            return "Expired"
        if not self.is_active:
            return "Inactive"
        if self.days_until_expiry <= 30:
            return f"Valid (expires in {self.days_until_expiry} days)"
        return "Valid"

    @property
    def common_name(self) -> str:
        """Extract Common Name from subject."""
        # Subject format: "CN=Name, O=Org, C=Country" or similar
        for part in self.subject.split(","):
            part = part.strip()
            if part.upper().startswith("CN="):
                return part[3:]
        return self.subject

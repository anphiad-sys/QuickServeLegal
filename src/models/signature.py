"""
QuickServe Legal - Signature Model

Records digital signature information for documents signed with AES.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class Signature(Base):
    """
    Digital signature record for a document.

    Stores the cryptographic signature applied via LAWTrust AES,
    linking the document to the signing attorney's certificate.
    """

    __tablename__ = "signatures"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Document being signed
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)

    # Signer information
    signer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    certificate_id: Mapped[int] = mapped_column(ForeignKey("certificates.id"), nullable=False)

    # Hash of the document at time of signing
    signed_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex

    # Signature data (base64-encoded PKCS#7 or similar)
    signature_value: Mapped[str] = mapped_column(Text, nullable=False)

    # LAWTrust reference (for verification with LAWTrust)
    lawtrust_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lawtrust_timestamp: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Signing method details
    signing_method: Mapped[str] = mapped_column(String(50), default="AES")  # AES, MOCK
    signature_algorithm: Mapped[str] = mapped_column(String(50), default="SHA256withRSA")

    # Timestamp server details (if timestamped)
    timestamp_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp_authority: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timestamped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # When the signature was created
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Signature {self.id} for document {self.document_id}>"

    @property
    def is_timestamped(self) -> bool:
        """Check if signature has a timestamp token."""
        return self.timestamp_token is not None

    @property
    def short_hash(self) -> str:
        """Get abbreviated hash for display."""
        return f"{self.signed_hash[:8]}...{self.signed_hash[-8:]}"

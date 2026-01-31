"""
QuickServe Legal - Document Model
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

if TYPE_CHECKING:
    from src.models.walk_in_service import WalkInService


class Document(Base):
    """A legal document served through QuickServe Legal."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # File details
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    content_type: Mapped[str] = mapped_column(String(100), default="application/pdf")

    # Source tracking (member upload vs PNSA walk-in)
    source_type: Mapped[str] = mapped_column(String(20), default="member", index=True)  # member, pnsa

    # Document hash (computed on upload for AES)
    document_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA-256 hex

    # Sender (uploader)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Recipient
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipient_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Matter details
    matter_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Download token (secure link)
    download_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Status tracking
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, downloaded, expired

    # AES Signing status
    signing_status: Mapped[str] = mapped_column(String(50), default="unsigned")  # unsigned, pending, signed
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    signed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    signature_id: Mapped[Optional[int]] = mapped_column(ForeignKey("signatures.id"), nullable=True)

    # Generated file variants
    signed_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Signed PDF
    with_placeholder_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # PDF with wet-ink placeholder

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    served_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When document was served (after signing)

    # Download details (for proof of service)
    download_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    download_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Email delivery tracking (SendGrid)
    email_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # SendGrid message ID
    email_status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, sent, delivered, opened, bounced, failed
    email_delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When delivered to recipient's mail server
    email_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When recipient opened email
    email_clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When recipient clicked link
    email_bounced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # If email bounced
    email_bounce_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Bounce explanation

    # OCR extracted data (populated when OCR is used)
    ocr_plaintiff: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ocr_defendant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ocr_case_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ocr_court_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ocr_pleading_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Walk-in service reference (for PNSA documents)
    walk_in_service: Mapped[Optional["WalkInService"]] = relationship(
        "WalkInService",
        back_populates="document",
        uselist=False,
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Document {self.id}: {self.original_filename} to {self.recipient_email}>"

    @property
    def is_served(self) -> bool:
        """Check if document has been served (per ECTA - when notification was sent)."""
        return self.served_at is not None or self.status == "served"

    @property
    def is_downloaded(self) -> bool:
        """Check if recipient has downloaded the document (optional confirmation)."""
        return self.downloaded_at is not None

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.token_expires_at and not self.is_downloaded

    @property
    def is_signed(self) -> bool:
        """Check if document has been signed with AES."""
        return self.signing_status == "signed" and self.signed_at is not None

    @property
    def can_be_served(self) -> bool:
        """Check if document can be served (must be signed if AES is required)."""
        # Import here to avoid circular dependency
        from src.config import settings
        if settings.AES_REQUIRED_FOR_SERVICE:
            return self.is_signed
        return True

    @property
    def signing_status_text(self) -> str:
        """Get human-readable signing status."""
        status_map = {
            "unsigned": "Not Signed",
            "pending": "Signing in Progress",
            "signed": "Signed",
        }
        return status_map.get(self.signing_status, self.signing_status)

    @property
    def is_email_delivered(self) -> bool:
        """Check if email was successfully delivered to recipient's mail server."""
        return self.email_status in ("delivered", "opened", "clicked")

    @property
    def is_email_opened(self) -> bool:
        """Check if recipient opened the email."""
        return self.email_status in ("opened", "clicked") or self.email_opened_at is not None

    @property
    def is_email_bounced(self) -> bool:
        """Check if email bounced."""
        return self.email_status in ("bounced", "failed")

    @property
    def email_status_text(self) -> str:
        """Get human-readable email delivery status."""
        status_map = {
            "pending": "Pending",
            "sent": "Sent",
            "delivered": "Delivered",
            "opened": "Opened",
            "clicked": "Link Clicked",
            "bounced": "Bounced",
            "failed": "Failed",
        }
        return status_map.get(self.email_status, self.email_status)

    @property
    def is_pnsa_document(self) -> bool:
        """Check if this document was served via PNSA walk-in."""
        return self.source_type == "pnsa"

    @property
    def source_type_text(self) -> str:
        """Get human-readable source type."""
        return "PNSA Walk-In" if self.source_type == "pnsa" else "Member Upload"


# Source type constants
class DocumentSourceType:
    """Document source type constants."""
    MEMBER = "member"  # Uploaded directly by QSL member
    PNSA = "pnsa"      # Walk-in service at PNSA branch

"""
QuickServe Legal - Audit Log Model

Provides an immutable audit trail with hash-chain integrity for legal compliance.
"""

import hashlib
import json
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class AuditLog(Base):
    """
    Immutable audit log entry with hash-chain integrity.

    Each entry contains a hash of itself and the previous entry's hash,
    creating a tamper-evident chain similar to blockchain.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Event details
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional JSON metadata for additional event-specific data
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Related entities (optional)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)

    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Hash chain for integrity verification
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA-256 hex
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA-256 hex

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog {self.id}: {self.event_type}>"

    @property
    def event_metadata(self) -> Optional[dict]:
        """Parse metadata_json as dictionary."""
        if self.metadata_json:
            try:
                return json.loads(self.metadata_json)
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def compute_hash(
        event_type: str,
        description: str,
        user_id: Optional[int],
        document_id: Optional[int],
        metadata_json: Optional[str],
        ip_address: Optional[str],
        previous_hash: Optional[str],
        created_at: datetime,
    ) -> str:
        """
        Compute SHA-256 hash of the audit entry data.

        This creates a deterministic hash of all important fields,
        ensuring any tampering can be detected.
        """
        # Create a canonical string representation
        data = {
            "event_type": event_type,
            "description": description,
            "user_id": user_id,
            "document_id": document_id,
            "metadata_json": metadata_json,
            "ip_address": ip_address,
            "previous_hash": previous_hash or "",
            "created_at": created_at.isoformat(),
        }

        # Sort keys for deterministic ordering
        canonical_string = json.dumps(data, sort_keys=True, separators=(",", ":"))

        # Compute SHA-256 hash
        return hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()

    def verify_hash(self) -> bool:
        """Verify that this entry's hash is valid."""
        computed = self.compute_hash(
            event_type=self.event_type,
            description=self.description,
            user_id=self.user_id,
            document_id=self.document_id,
            metadata_json=self.metadata_json,
            ip_address=self.ip_address,
            previous_hash=self.previous_hash,
            created_at=self.created_at,
        )
        return computed == self.entry_hash


# Event type constants
class AuditEventType:
    """Standard audit event types for QuickServe Legal."""

    # User events
    USER_REGISTERED = "user.registered"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_VERIFIED = "user.verified"

    # Document events
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_HASH_COMPUTED = "document.hash_computed"
    DOCUMENT_SERVED = "document.served"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_EXPIRED = "document.expired"

    # Signing events
    SIGNATURE_REQUESTED = "signature.requested"
    SIGNATURE_PLACEHOLDER_ADDED = "signature.placeholder_added"
    SIGNATURE_COMPLETED = "signature.completed"
    SIGNATURE_FAILED = "signature.failed"

    # Certificate events
    CERTIFICATE_REGISTERED = "certificate.registered"
    CERTIFICATE_ACTIVATED = "certificate.activated"
    CERTIFICATE_DEACTIVATED = "certificate.deactivated"
    CERTIFICATE_REVOKED = "certificate.revoked"
    CERTIFICATE_EXPIRED = "certificate.expired"

    # Notification events
    NOTIFICATION_SENT = "notification.sent"
    REMINDER_SENT = "notification.reminder_sent"

    # Email tracking events
    EMAIL_STATUS_UPDATED = "email.status_updated"
    EMAIL_DELIVERED = "email.delivered"
    EMAIL_OPENED = "email.opened"
    EMAIL_CLICKED = "email.clicked"
    EMAIL_BOUNCED = "email.bounced"
    EMAIL_FAILED = "email.failed"

    # System events
    PROOF_OF_SERVICE_GENERATED = "system.proof_of_service_generated"
    COURT_CERTIFICATE_GENERATED = "system.court_certificate_generated"
    STAMPED_PDF_GENERATED = "system.stamped_pdf_generated"

    # PNSA Branch events
    PNSA_OPERATOR_LOGIN = "pnsa.operator_login"
    PNSA_OPERATOR_LOGOUT = "pnsa.operator_logout"
    PNSA_DOCUMENT_SCANNED = "pnsa.document_scanned"
    PNSA_DOCUMENT_REVIEWED = "pnsa.document_reviewed"
    PNSA_DOCUMENT_SERVED = "pnsa.document_served"
    PNSA_CONFIRMATION_PRINTED = "pnsa.confirmation_printed"
    PNSA_SERVICE_FEE_RECORDED = "pnsa.service_fee_recorded"

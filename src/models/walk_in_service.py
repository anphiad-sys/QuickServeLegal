"""
QuickServe Legal - Walk-In Service Model

Records walk-in document service processed at PNSA branches.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Numeric, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

if TYPE_CHECKING:
    from src.models.branch import Branch
    from src.models.branch_operator import BranchOperator
    from src.models.document import Document
    from src.models.user import User


class WalkInService(Base):
    """A walk-in document service record from a PNSA branch."""

    __tablename__ = "walk_in_services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Related document (created during the service)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)

    # Branch and operator who processed this
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("branch_operators.id"), nullable=False, index=True)

    # Messenger details (the person who physically brought the document)
    messenger_name: Mapped[str] = mapped_column(String(255), nullable=False)
    messenger_id_number: Mapped[str] = mapped_column(String(20), nullable=False)
    messenger_id_type: Mapped[str] = mapped_column(String(50), default="RSA ID")

    # Serving attorney (extracted from document / provided by messenger)
    serving_attorney_name: Mapped[str] = mapped_column(String(255), nullable=False)
    serving_attorney_firm: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    serving_attorney_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    serving_attorney_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    serving_attorney_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps for the service workflow
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    served_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmations_printed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Billing details (set when recipient is confirmed)
    billed_to_member_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    service_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    billing_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    billed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # OCR confidence for extracted data
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Additional notes from operator
    operator_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="walk_in_service")
    branch: Mapped["Branch"] = relationship("Branch", back_populates="walk_in_services")
    operator: Mapped["BranchOperator"] = relationship("BranchOperator", back_populates="walk_in_services")
    billed_to_member: Mapped[Optional["User"]] = relationship("User", foreign_keys=[billed_to_member_id])

    def __repr__(self) -> str:
        return f"<WalkInService {self.id}: {self.serving_attorney_name} via {self.branch_id}>"

    @property
    def is_served(self) -> bool:
        """Check if the document has been served."""
        return self.served_at is not None

    @property
    def is_paid(self) -> bool:
        """Check if the service fee has been paid."""
        return self.billing_status == "paid"

    @property
    def status_text(self) -> str:
        """Get human-readable status."""
        status_map = {
            "pending": "Pending Review",
            "reviewed": "Reviewed",
            "served": "Served",
            "completed": "Completed",
            "cancelled": "Cancelled",
        }
        return status_map.get(self.status, self.status)

    @property
    def billing_status_text(self) -> str:
        """Get human-readable billing status."""
        status_map = {
            "pending": "Pending",
            "invoiced": "Invoiced",
            "paid": "Paid",
            "waived": "Waived",
        }
        return status_map.get(self.billing_status, self.billing_status)


# Status constants
class WalkInServiceStatus:
    """Walk-in service status constants."""
    PENDING = "pending"      # Document scanned, awaiting review
    REVIEWED = "reviewed"    # Operator reviewed OCR data
    SERVED = "served"        # Document served to recipient
    COMPLETED = "completed"  # Confirmation printed, process complete
    CANCELLED = "cancelled"  # Service cancelled


class BillingStatus:
    """Billing status constants."""
    PENDING = "pending"    # Fee recorded, not yet invoiced
    INVOICED = "invoiced"  # Invoice sent to member
    PAID = "paid"          # Payment received
    WAIVED = "waived"      # Fee waived (e.g., for promotional reasons)


# ID types accepted
ID_TYPES = [
    "RSA ID",
    "RSA Passport",
    "Foreign Passport",
    "Driver's License",
    "Work Permit",
]

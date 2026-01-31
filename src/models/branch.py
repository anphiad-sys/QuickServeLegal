"""
QuickServe Legal - Branch Model

PNSA branch locations for walk-in document service.
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

if TYPE_CHECKING:
    from src.models.branch_operator import BranchOperator
    from src.models.walk_in_service import WalkInService


class Branch(Base):
    """A PNSA branch location that can process walk-in document service."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Branch identification
    branch_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Location
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Contact
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    operators: Mapped[List["BranchOperator"]] = relationship(
        "BranchOperator",
        back_populates="branch",
        lazy="selectin"
    )
    walk_in_services: Mapped[List["WalkInService"]] = relationship(
        "WalkInService",
        back_populates="branch",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Branch {self.branch_code}: {self.branch_name}>"

    @property
    def full_address(self) -> str:
        """Get formatted full address."""
        parts = [self.address, self.city]
        if self.postal_code:
            parts.append(self.postal_code)
        parts.append(self.province)
        return ", ".join(parts)


# South African provinces
SA_PROVINCES = [
    "Eastern Cape",
    "Free State",
    "Gauteng",
    "KwaZulu-Natal",
    "Limpopo",
    "Mpumalanga",
    "Northern Cape",
    "North West",
    "Western Cape",
]

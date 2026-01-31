"""
QuickServe Legal - Branch Operator Model

PNSA branch staff who process walk-in document service.
Separate from the User model as these are not QSL members.
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

if TYPE_CHECKING:
    from src.models.branch import Branch
    from src.models.walk_in_service import WalkInService


class BranchOperator(Base):
    """A PNSA branch operator who processes walk-in document service."""

    __tablename__ = "branch_operators"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Branch association
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)

    # Identification
    employee_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Authentication
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Contact
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Role/permissions (for future expansion)
    role: Mapped[str] = mapped_column(String(50), default="operator")  # operator, supervisor, admin

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    branch: Mapped["Branch"] = relationship("Branch", back_populates="operators")
    walk_in_services: Mapped[List["WalkInService"]] = relationship(
        "WalkInService",
        back_populates="operator",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<BranchOperator {self.employee_number}: {self.full_name}>"

    @property
    def display_name(self) -> str:
        """Get display name for UI."""
        return f"{self.full_name} ({self.employee_number})"


# Operator roles
class OperatorRole:
    """Branch operator role constants."""
    OPERATOR = "operator"      # Standard operator - can process walk-in services
    SUPERVISOR = "supervisor"  # Can view reports and manage operators
    ADMIN = "admin"           # Full access including branch settings

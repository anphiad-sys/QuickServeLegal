"""
QuickServe Legal - Billing Tracking

Simple service fee tracking for PNSA walk-in services.
No payment integration yet - just tracks fees and billing status.
"""

from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.walk_in_service import WalkInService, BillingStatus
from src.timestamps import now_utc
from src.models.user import User
from src.models.branch import Branch


# Get service fee from settings (default R50.00)
def get_service_fee() -> Decimal:
    """Get the current PNSA service fee."""
    fee = getattr(settings, 'PNSA_SERVICE_FEE', "50.00")
    if isinstance(fee, Decimal):
        return fee
    return Decimal(str(fee))


async def record_walk_in_service_fee(
    db: AsyncSession,
    walk_in_service: WalkInService,
    member_id: int,
    fee_amount: Optional[Decimal] = None,
) -> WalkInService:
    """
    Record the service fee for a walk-in service.

    Args:
        db: Database session
        walk_in_service: The walk-in service record
        member_id: ID of the QSL member being billed
        fee_amount: Fee amount (defaults to PNSA_SERVICE_FEE)

    Returns:
        Updated WalkInService record
    """
    if fee_amount is None:
        fee_amount = get_service_fee()

    walk_in_service.billed_to_member_id = member_id
    walk_in_service.service_fee = fee_amount
    walk_in_service.billing_status = BillingStatus.PENDING

    await db.commit()
    await db.refresh(walk_in_service)
    return walk_in_service


async def get_member_pending_charges(
    db: AsyncSession,
    member_id: int,
) -> List[WalkInService]:
    """
    Get all pending charges for a QSL member.

    Args:
        db: Database session
        member_id: ID of the QSL member

    Returns:
        List of WalkInService records with pending billing
    """
    result = await db.execute(
        select(WalkInService)
        .where(
            and_(
                WalkInService.billed_to_member_id == member_id,
                WalkInService.billing_status == BillingStatus.PENDING,
            )
        )
        .order_by(WalkInService.created_at.desc())
    )
    return list(result.scalars().all())


async def get_member_total_pending(
    db: AsyncSession,
    member_id: int,
) -> Decimal:
    """
    Get the total pending charges for a QSL member.

    Args:
        db: Database session
        member_id: ID of the QSL member

    Returns:
        Total pending amount
    """
    result = await db.execute(
        select(func.sum(WalkInService.service_fee))
        .where(
            and_(
                WalkInService.billed_to_member_id == member_id,
                WalkInService.billing_status == BillingStatus.PENDING,
            )
        )
    )
    total = result.scalar_one_or_none()
    return total or Decimal("0.00")


async def get_member_billing_history(
    db: AsyncSession,
    member_id: int,
    limit: int = 50,
) -> List[WalkInService]:
    """
    Get billing history for a QSL member.

    Args:
        db: Database session
        member_id: ID of the QSL member
        limit: Maximum records to return

    Returns:
        List of WalkInService records
    """
    result = await db.execute(
        select(WalkInService)
        .where(WalkInService.billed_to_member_id == member_id)
        .order_by(WalkInService.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_as_invoiced(
    db: AsyncSession,
    walk_in_service: WalkInService,
) -> WalkInService:
    """Mark a walk-in service fee as invoiced."""
    walk_in_service.billing_status = BillingStatus.INVOICED
    walk_in_service.billed_at = now_utc()
    await db.commit()
    await db.refresh(walk_in_service)
    return walk_in_service


async def mark_as_paid(
    db: AsyncSession,
    walk_in_service: WalkInService,
) -> WalkInService:
    """Mark a walk-in service fee as paid."""
    walk_in_service.billing_status = BillingStatus.PAID
    walk_in_service.paid_at = now_utc()
    await db.commit()
    await db.refresh(walk_in_service)
    return walk_in_service


async def waive_fee(
    db: AsyncSession,
    walk_in_service: WalkInService,
) -> WalkInService:
    """Waive the service fee for a walk-in service."""
    walk_in_service.billing_status = BillingStatus.WAIVED
    await db.commit()
    await db.refresh(walk_in_service)
    return walk_in_service


# =============================================================================
# BRANCH REPORTING
# =============================================================================

async def get_branch_daily_summary(
    db: AsyncSession,
    branch_id: int,
    target_date: Optional[date] = None,
) -> dict:
    """
    Get daily summary for a branch.

    Args:
        db: Database session
        branch_id: ID of the branch
        target_date: Date to summarize (defaults to today)

    Returns:
        Dictionary with summary data
    """
    if target_date is None:
        target_date = now_utc().date()

    # Get start and end of day
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Get all services for the day
    result = await db.execute(
        select(WalkInService)
        .where(
            and_(
                WalkInService.branch_id == branch_id,
                WalkInService.created_at >= start_of_day,
                WalkInService.created_at <= end_of_day,
            )
        )
    )
    services = list(result.scalars().all())

    # Calculate totals
    total_services = len(services)
    total_served = sum(1 for s in services if s.is_served)
    total_fees = sum(s.service_fee for s in services)

    # By status
    status_counts = {}
    for service in services:
        status_counts[service.status] = status_counts.get(service.status, 0) + 1

    return {
        "date": target_date.isoformat(),
        "branch_id": branch_id,
        "total_services": total_services,
        "total_served": total_served,
        "total_pending": total_services - total_served,
        "total_fees": total_fees,
        "status_breakdown": status_counts,
    }


async def get_branch_monthly_summary(
    db: AsyncSession,
    branch_id: int,
    year: int,
    month: int,
) -> dict:
    """
    Get monthly summary for a branch.

    Args:
        db: Database session
        branch_id: ID of the branch
        year: Year
        month: Month (1-12)

    Returns:
        Dictionary with summary data
    """
    # Get start and end of month
    start_of_month = datetime(year, month, 1)
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1)
    else:
        end_of_month = datetime(year, month + 1, 1)

    # Get all services for the month
    result = await db.execute(
        select(WalkInService)
        .where(
            and_(
                WalkInService.branch_id == branch_id,
                WalkInService.created_at >= start_of_month,
                WalkInService.created_at < end_of_month,
            )
        )
    )
    services = list(result.scalars().all())

    # Calculate totals
    total_services = len(services)
    total_served = sum(1 for s in services if s.is_served)
    total_fees = sum(s.service_fee for s in services)
    total_paid = sum(s.service_fee for s in services if s.billing_status == BillingStatus.PAID)

    return {
        "year": year,
        "month": month,
        "branch_id": branch_id,
        "total_services": total_services,
        "total_served": total_served,
        "total_fees": total_fees,
        "total_paid": total_paid,
        "outstanding": total_fees - total_paid,
    }


async def get_operator_daily_stats(
    db: AsyncSession,
    operator_id: int,
    target_date: Optional[date] = None,
) -> dict:
    """
    Get daily stats for a specific operator.

    Args:
        db: Database session
        operator_id: ID of the operator
        target_date: Date to summarize (defaults to today)

    Returns:
        Dictionary with stats
    """
    if target_date is None:
        target_date = now_utc().date()

    # Get start and end of day
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Get all services for the day by this operator
    result = await db.execute(
        select(WalkInService)
        .where(
            and_(
                WalkInService.operator_id == operator_id,
                WalkInService.created_at >= start_of_day,
                WalkInService.created_at <= end_of_day,
            )
        )
    )
    services = list(result.scalars().all())

    return {
        "date": target_date.isoformat(),
        "operator_id": operator_id,
        "total_services": len(services),
        "total_served": sum(1 for s in services if s.is_served),
        "total_fees": sum(s.service_fee for s in services),
    }

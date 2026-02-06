"""
QuickServe Legal - Audit Service

Provides immutable audit logging with hash-chain integrity verification.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog, AuditEventType
from src.timestamps import now_utc


async def log_event(
    db: AsyncSession,
    event_type: str,
    description: str,
    user_id: Optional[int] = None,
    document_id: Optional[int] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Create an immutable audit log entry with hash chain.

    Args:
        db: Database session
        event_type: Type of event (use AuditEventType constants)
        description: Human-readable description of the event
        user_id: Optional ID of user who triggered the event
        document_id: Optional ID of related document
        metadata: Optional additional data as dictionary
        ip_address: Optional client IP address
        user_agent: Optional client user agent

    Returns:
        The created AuditLog entry
    """
    # Get the previous entry's hash for chain integrity
    previous_entry = await get_last_audit_entry(db)
    previous_hash = previous_entry.entry_hash if previous_entry else None

    # Serialize metadata
    metadata_json = json.dumps(metadata, sort_keys=True) if metadata else None

    # Truncate user agent if too long
    if user_agent and len(user_agent) > 500:
        user_agent = user_agent[:500]

    # Create timestamp
    created_at = now_utc()

    # Compute hash of this entry
    entry_hash = AuditLog.compute_hash(
        event_type=event_type,
        description=description,
        user_id=user_id,
        document_id=document_id,
        metadata_json=metadata_json,
        ip_address=ip_address,
        previous_hash=previous_hash,
        created_at=created_at,
    )

    # Create the audit log entry
    audit_entry = AuditLog(
        event_type=event_type,
        description=description,
        user_id=user_id,
        document_id=document_id,
        metadata_json=metadata_json,
        ip_address=ip_address,
        user_agent=user_agent,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        created_at=created_at,
    )

    db.add(audit_entry)
    await db.commit()
    await db.refresh(audit_entry)

    return audit_entry


async def get_last_audit_entry(db: AsyncSession) -> Optional[AuditLog]:
    """Get the most recent audit log entry."""
    result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.id)).limit(1)
    )
    return result.scalar_one_or_none()


async def get_document_audit_trail(
    db: AsyncSession,
    document_id: int,
    limit: int = 100,
) -> List[AuditLog]:
    """
    Get all audit entries for a specific document.

    Args:
        db: Database session
        document_id: ID of the document
        limit: Maximum number of entries to return

    Returns:
        List of AuditLog entries in chronological order
    """
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.document_id == document_id)
        .order_by(AuditLog.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_user_audit_trail(
    db: AsyncSession,
    user_id: int,
    limit: int = 100,
) -> List[AuditLog]:
    """
    Get all audit entries for a specific user.

    Args:
        db: Database session
        user_id: ID of the user
        limit: Maximum number of entries to return

    Returns:
        List of AuditLog entries in reverse chronological order
    """
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def verify_audit_chain_integrity(
    db: AsyncSession,
    start_id: Optional[int] = None,
    end_id: Optional[int] = None,
) -> dict:
    """
    Verify the integrity of the audit log hash chain.

    Args:
        db: Database session
        start_id: Optional starting entry ID (inclusive)
        end_id: Optional ending entry ID (inclusive)

    Returns:
        Dictionary with verification results:
        {
            "valid": bool,
            "entries_checked": int,
            "first_invalid_id": int or None,
            "error": str or None
        }
    """
    # Build query
    query = select(AuditLog).order_by(AuditLog.id.asc())

    if start_id is not None:
        query = query.where(AuditLog.id >= start_id)
    if end_id is not None:
        query = query.where(AuditLog.id <= end_id)

    result = await db.execute(query)
    entries = list(result.scalars().all())

    if not entries:
        return {
            "valid": True,
            "entries_checked": 0,
            "first_invalid_id": None,
            "error": None,
        }

    entries_checked = 0
    previous_hash = None

    for entry in entries:
        entries_checked += 1

        # Verify this entry's hash
        if not entry.verify_hash():
            return {
                "valid": False,
                "entries_checked": entries_checked,
                "first_invalid_id": entry.id,
                "error": f"Entry {entry.id} hash mismatch - data may have been tampered",
            }

        # Verify chain linkage (except for first entry)
        if previous_hash is not None and entry.previous_hash != previous_hash:
            return {
                "valid": False,
                "entries_checked": entries_checked,
                "first_invalid_id": entry.id,
                "error": f"Entry {entry.id} chain broken - previous_hash mismatch",
            }

        previous_hash = entry.entry_hash

    return {
        "valid": True,
        "entries_checked": entries_checked,
        "first_invalid_id": None,
        "error": None,
    }


def export_audit_trail_to_json(entries: List[AuditLog]) -> str:
    """
    Export audit trail entries to JSON format.

    Args:
        entries: List of AuditLog entries

    Returns:
        JSON string
    """
    data = {
        "export_timestamp": now_utc().isoformat(),
        "entry_count": len(entries),
        "entries": [
            {
                "id": entry.id,
                "event_type": entry.event_type,
                "description": entry.description,
                "user_id": entry.user_id,
                "document_id": entry.document_id,
                "metadata": entry.event_metadata,
                "ip_address": entry.ip_address,
                "previous_hash": entry.previous_hash,
                "entry_hash": entry.entry_hash,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ],
    }

    return json.dumps(data, indent=2)


async def log_document_event(
    db: AsyncSession,
    event_type: str,
    document_id: int,
    user_id: int,
    description: str,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Convenience function to log a document-related event.
    """
    return await log_event(
        db=db,
        event_type=event_type,
        description=description,
        user_id=user_id,
        document_id=document_id,
        metadata=metadata,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def log_signing_event(
    db: AsyncSession,
    event_type: str,
    document_id: int,
    user_id: int,
    certificate_id: Optional[int] = None,
    signature_id: Optional[int] = None,
    description: str = "",
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Convenience function to log a signing-related event.
    """
    metadata = {}
    if certificate_id:
        metadata["certificate_id"] = certificate_id
    if signature_id:
        metadata["signature_id"] = signature_id

    return await log_event(
        db=db,
        event_type=event_type,
        description=description,
        user_id=user_id,
        document_id=document_id,
        metadata=metadata if metadata else None,
        ip_address=ip_address,
    )

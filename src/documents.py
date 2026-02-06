"""
QuickServe Legal - Document Upload/Download Logic
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile, HTTPException, status

from src.config import settings
from src.models.document import Document
from src.timestamps import now_utc
from src.models.user import User


def generate_download_token() -> str:
    """Generate a secure random download token."""
    return secrets.token_urlsafe(32)


def generate_stored_filename(original_filename: str) -> str:
    """Generate a unique filename for storage."""
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


def validate_file(file: UploadFile) -> None:
    """Validate uploaded file (type and size)."""
    # Check file extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only PDF files are allowed. Got: {ext}"
            )

    # Check content type
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )


async def save_uploaded_file(file: UploadFile, stored_filename: str) -> int:
    """
    Save uploaded file to disk using streaming to enforce size limit.

    Reads in chunks so oversized files are rejected without consuming
    all available memory.

    Returns the file size in bytes.
    """
    file_path = settings.UPLOAD_DIR / stored_filename
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    chunk_size = 64 * 1024  # 64KB chunks
    file_size = 0

    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > max_size:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB"
                    )
                f.write(chunk)
    except HTTPException:
        # Clean up partial file on size rejection
        if file_path.exists():
            file_path.unlink()
        raise

    return file_size


def get_file_path(stored_filename: str) -> Path:
    """Get the full path to a stored file."""
    return settings.UPLOAD_DIR / stored_filename


async def create_document(
    db: AsyncSession,
    file: UploadFile,
    sender: User,
    recipient_email: str,
    recipient_name: Optional[str] = None,
    matter_reference: Optional[str] = None,
    description: Optional[str] = None,
) -> Document:
    """
    Create a new document record and save the file.
    """
    # Validate file
    validate_file(file)

    # Generate filenames and token
    original_filename = file.filename or "document.pdf"
    stored_filename = generate_stored_filename(original_filename)
    download_token = generate_download_token()

    # Save file to disk
    file_size = await save_uploaded_file(file, stored_filename)

    # Calculate token expiry
    token_expires_at = now_utc() + timedelta(hours=settings.DOWNLOAD_TOKEN_EXPIRE_HOURS)

    # Create document record
    document = Document(
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_size=file_size,
        content_type="application/pdf",
        sender_id=sender.id,
        sender_email=sender.email,
        sender_name=sender.full_name,
        recipient_email=recipient_email.lower().strip(),
        recipient_name=recipient_name.strip() if recipient_name else None,
        matter_reference=matter_reference.strip() if matter_reference else None,
        description=description.strip() if description else None,
        download_token=download_token,
        token_expires_at=token_expires_at,
        status="pending",
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    return document


async def get_document_by_token(db: AsyncSession, token: str) -> Optional[Document]:
    """Get a document by its download token."""
    result = await db.execute(
        select(Document).where(Document.download_token == token)
    )
    return result.scalar_one_or_none()


async def get_document_by_id(db: AsyncSession, document_id: int) -> Optional[Document]:
    """Get a document by its ID."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    return result.scalar_one_or_none()


async def get_user_sent_documents(db: AsyncSession, user_id: int, limit: int = 50) -> List[Document]:
    """Get documents sent by a user."""
    result = await db.execute(
        select(Document)
        .where(Document.sender_id == user_id)
        .order_by(Document.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_user_received_documents(db: AsyncSession, user_email: str, limit: int = 50) -> List[Document]:
    """Get documents sent to a user (by email)."""
    result = await db.execute(
        select(Document)
        .where(Document.recipient_email == user_email.lower())
        .order_by(Document.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_document_served(
    db: AsyncSession,
    document: Document,
) -> Document:
    """
    Mark a document as served (per ECTA Section 23).

    Under ECTA, a document is considered 'received' when it enters the
    recipient's information system and is capable of being retrieved.
    This occurs when the notification email is sent.
    """
    document.status = "served"
    document.served_at = now_utc()
    document.notified_at = now_utc()

    await db.commit()
    await db.refresh(document)

    return document


async def try_mark_document_downloaded(
    db: AsyncSession,
    document: Document,
    ip_address: str,
    user_agent: str,
) -> int:
    """
    Atomically mark a document as downloaded using UPDATE ... WHERE.

    Returns the number of rows affected (1 if marked, 0 if already downloaded).
    This prevents race conditions where concurrent requests both mark the same
    document as downloaded.
    """
    from sqlalchemy import update

    truncated_ua = user_agent[:500] if user_agent else None
    now = now_utc()

    result = await db.execute(
        update(Document)
        .where(Document.id == document.id)
        .where(Document.downloaded_at.is_(None))  # Atomic check
        .values(
            downloaded_at=now,
            download_ip=ip_address,
            download_user_agent=truncated_ua,
        )
    )
    rows_affected = result.rowcount
    await db.commit()

    if rows_affected > 0:
        await db.refresh(document)

    return rows_affected


def get_document_stats(documents: List[Document]) -> dict:
    """Calculate document statistics."""
    stats = {
        "served": len(documents),
        "pending": 0,
        "confirmed": 0,
    }

    for doc in documents:
        if doc.is_downloaded:
            stats["confirmed"] += 1
        else:
            stats["pending"] += 1

    return stats

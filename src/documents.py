"""
QuickServe Legal - Document Upload/Download Logic
"""

import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile, HTTPException, status

from src.config import settings
from src.models.document import Document
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
    Save uploaded file to disk.

    Returns the file size in bytes.
    """
    file_path = settings.UPLOAD_DIR / stored_filename

    # Read and save file
    content = await file.read()
    file_size = len(content)

    # Check file size
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB"
        )

    # Write to disk
    with open(file_path, "wb") as f:
        f.write(content)

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
    token_expires_at = datetime.utcnow() + timedelta(hours=settings.DOWNLOAD_TOKEN_EXPIRE_HOURS)

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
    document.served_at = datetime.utcnow()
    document.notified_at = datetime.utcnow()

    await db.commit()
    await db.refresh(document)

    return document


async def mark_document_downloaded(
    db: AsyncSession,
    document: Document,
    ip_address: str,
    user_agent: str,
) -> Document:
    """Mark a document as downloaded (additional confirmation, not required for service)."""
    document.downloaded_at = datetime.utcnow()
    document.download_ip = ip_address
    document.download_user_agent = user_agent[:500] if user_agent else None  # Truncate long user agents

    await db.commit()
    await db.refresh(document)

    return document


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

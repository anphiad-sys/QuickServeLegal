"""
Tests for document upload, download, token expiry, and proof of service.

TDD: These tests define expected behavior for the document service flow.
"""

import io
from datetime import datetime, timedelta

import pytest
from tests.conftest import csrf_data
from src.documents import (
    generate_download_token,
    generate_stored_filename,
    validate_file,
    get_document_stats,
)
from src.models.document import Document


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

class TestDownloadToken:
    def test_token_is_url_safe(self):
        """Download tokens should be URL-safe strings."""
        token = generate_download_token()
        assert isinstance(token, str)
        assert len(token) > 20  # Sufficiently random

    def test_tokens_are_unique(self):
        """Each token should be unique."""
        tokens = {generate_download_token() for _ in range(100)}
        assert len(tokens) == 100


class TestStoredFilename:
    def test_preserves_extension(self):
        """Stored filename should preserve the original file extension."""
        result = generate_stored_filename("document.pdf")
        assert result.endswith(".pdf")

    def test_generates_unique_names(self):
        """Each stored filename should be unique."""
        names = {generate_stored_filename("doc.pdf") for _ in range(100)}
        assert len(names) == 100

    def test_lowercases_extension(self):
        """Extension should be lowercase."""
        result = generate_stored_filename("document.PDF")
        assert result.endswith(".pdf")


# =============================================================================
# FILE VALIDATION
# =============================================================================

class TestFileValidation:
    def test_rejects_non_pdf_extension(self):
        """Non-PDF files should be rejected."""
        from unittest.mock import MagicMock
        from fastapi import HTTPException

        mock_file = MagicMock()
        mock_file.filename = "document.docx"
        mock_file.content_type = "application/msword"

        with pytest.raises(HTTPException) as exc_info:
            validate_file(mock_file)
        assert exc_info.value.status_code == 400

    def test_accepts_pdf(self):
        """PDF files should be accepted."""
        from unittest.mock import MagicMock

        mock_file = MagicMock()
        mock_file.filename = "document.pdf"
        mock_file.content_type = "application/pdf"

        # Should not raise
        validate_file(mock_file)

    def test_rejects_wrong_content_type(self):
        """Files with wrong content type should be rejected even with .pdf extension."""
        from unittest.mock import MagicMock
        from fastapi import HTTPException

        mock_file = MagicMock()
        mock_file.filename = "document.pdf"
        mock_file.content_type = "text/html"

        with pytest.raises(HTTPException) as exc_info:
            validate_file(mock_file)
        assert exc_info.value.status_code == 400


# =============================================================================
# DOCUMENT MODEL PROPERTIES
# =============================================================================

class TestDocumentProperties:
    async def test_is_downloaded_when_downloaded_at_set(self, db, test_user):
        """Document should be marked as downloaded when downloaded_at is set."""
        doc = Document(
            original_filename="t.pdf", stored_filename="s.pdf", file_size=100,
            sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
            recipient_email="r@e.com", download_token="tok1",
            token_expires_at=datetime.utcnow() + timedelta(hours=1), status="pending",
            downloaded_at=datetime.utcnow(),
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        assert doc.is_downloaded is True

    async def test_not_downloaded_when_downloaded_at_none(self, db, test_user):
        """Document should not be downloaded when downloaded_at is None."""
        doc = Document(
            original_filename="t.pdf", stored_filename="s2.pdf", file_size=100,
            sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
            recipient_email="r@e.com", download_token="tok2",
            token_expires_at=datetime.utcnow() + timedelta(hours=1), status="pending",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        assert doc.is_downloaded is False

    async def test_is_expired_when_past_expiry(self, db, test_user):
        """Document should be expired when token_expires_at is in the past."""
        doc = Document(
            original_filename="t.pdf", stored_filename="s3.pdf", file_size=100,
            sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
            recipient_email="r@e.com", download_token="tok3",
            token_expires_at=datetime.utcnow() - timedelta(hours=1), status="pending",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        assert doc.is_expired is True

    async def test_not_expired_when_future_expiry(self, db, test_user):
        """Document should not be expired when token_expires_at is in the future."""
        doc = Document(
            original_filename="t.pdf", stored_filename="s4.pdf", file_size=100,
            sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
            recipient_email="r@e.com", download_token="tok4",
            token_expires_at=datetime.utcnow() + timedelta(hours=1), status="pending",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        assert doc.is_expired is False

    async def test_not_expired_if_already_downloaded(self, db, test_user):
        """Document should not be expired if already downloaded even if past expiry."""
        doc = Document(
            original_filename="t.pdf", stored_filename="s5.pdf", file_size=100,
            sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
            recipient_email="r@e.com", download_token="tok5",
            token_expires_at=datetime.utcnow() - timedelta(hours=1), status="pending",
            downloaded_at=datetime.utcnow() - timedelta(hours=2),
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        assert doc.is_expired is False

    async def test_is_served_when_served_at_set(self, db, test_user):
        """Document should be served when served_at is set."""
        doc = Document(
            original_filename="t.pdf", stored_filename="s6.pdf", file_size=100,
            sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
            recipient_email="r@e.com", download_token="tok6",
            token_expires_at=datetime.utcnow() + timedelta(hours=1), status="served",
            served_at=datetime.utcnow(),
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        assert doc.is_served is True

    async def test_not_served_when_pending(self, db, test_user):
        """Document should not be served when status is pending."""
        doc = Document(
            original_filename="t.pdf", stored_filename="s7.pdf", file_size=100,
            sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
            recipient_email="r@e.com", download_token="tok7",
            token_expires_at=datetime.utcnow() + timedelta(hours=1), status="pending",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        assert doc.is_served is False


# =============================================================================
# DOCUMENT STATS
# =============================================================================

class TestDocumentStats:
    def test_empty_documents(self):
        """Stats for empty list should show zeros."""
        stats = get_document_stats([])
        assert stats["served"] == 0
        assert stats["pending"] == 0
        assert stats["confirmed"] == 0

    async def test_mixed_documents(self, db, test_user):
        """Stats should correctly count downloaded and pending."""
        docs = []
        for i in range(3):
            doc = Document(
                original_filename="t.pdf", stored_filename=f"stat{i}.pdf", file_size=100,
                sender_id=test_user.id, sender_email=test_user.email, sender_name=test_user.full_name,
                recipient_email="r@e.com", download_token=f"stattok{i}",
                token_expires_at=datetime.utcnow() + timedelta(hours=1), status="pending",
                downloaded_at=datetime.utcnow() if i < 2 else None,
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            docs.append(doc)

        stats = get_document_stats(docs)
        assert stats["served"] == 3
        assert stats["confirmed"] == 2
        assert stats["pending"] == 1


# =============================================================================
# DOCUMENT UPLOAD (via HTTP)
# =============================================================================

class TestDocumentUpload:
    async def test_upload_requires_auth(self, client):
        """Upload should redirect unauthenticated users."""
        import io
        pdf_content = b"%PDF-1.4 test"
        response = await client.post(
            "/upload",
            data=csrf_data(client, {"recipient_email": "test@example.com"}),
            files={"document": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/login" in response.headers.get("location", "")

    async def test_upload_valid_pdf(self, auth_client):
        """Uploading a valid PDF should succeed."""
        # Create a minimal PDF content
        pdf_content = b"%PDF-1.4 minimal test content"
        response = await auth_client.post(
            "/upload",
            data=csrf_data(auth_client, {
                "recipient_email": "recipient@example.com",
                "recipient_name": "Recipient",
                "matter_reference": "CASE/2024/001",
            }),
            files={"document": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
            follow_redirects=False,
        )
        # Should redirect to success page or signing page
        assert response.status_code == 303


# =============================================================================
# DOCUMENT DOWNLOAD
# =============================================================================

class TestDocumentDownload:
    async def test_download_invalid_token(self, client):
        """Invalid download token should return 404."""
        response = await client.get("/download/nonexistent-token")
        assert response.status_code == 404

    async def test_download_expired_token(self, client, db, test_user):
        """Expired download token should return 410."""
        # Create a document with expired token
        doc = Document(
            original_filename="test.pdf",
            stored_filename="stored_test.pdf",
            file_size=1000,
            content_type="application/pdf",
            sender_id=test_user.id,
            sender_email=test_user.email,
            sender_name=test_user.full_name,
            recipient_email="recipient@example.com",
            download_token="expired-test-token-123",
            token_expires_at=datetime.utcnow() - timedelta(hours=1),
            status="pending",
        )
        db.add(doc)
        await db.commit()

        response = await client.get("/download/expired-test-token-123")
        assert response.status_code == 410

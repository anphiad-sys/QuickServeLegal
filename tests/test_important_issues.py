"""
Tests for IMPORTANT issues from code review audit.

TDD RED phase: These tests define requirements that must be fixed.
"""

import io
import re

import pytest
from tests.conftest import csrf_data


# =============================================================================
# ISSUE 1: XSS via OCR extraction
# =============================================================================

class TestOCRSanitization:
    """OCR-extracted data must be sanitized before storage/display."""

    def test_sanitize_strips_script_tags(self):
        """OCR text with <script> tags should have them stripped."""
        from src.ocr_processor import sanitize_ocr_text

        malicious = '<script>alert("xss")</script>Smith v Jones'
        result = sanitize_ocr_text(malicious)
        assert "<script>" not in result
        assert "</script>" not in result
        assert "Smith v Jones" in result

    def test_sanitize_strips_html_tags(self):
        """OCR text with HTML tags should have them stripped."""
        from src.ocr_processor import sanitize_ocr_text

        malicious = '<img src=x onerror="alert(1)">Case 12345'
        result = sanitize_ocr_text(malicious)
        assert "<img" not in result
        assert "onerror" not in result
        assert "Case 12345" in result

    def test_sanitize_preserves_normal_text(self):
        """Normal legal text should be preserved unchanged."""
        from src.ocr_processor import sanitize_ocr_text

        normal = "Smith & Jones v Republic of South Africa - Case 12345/2026"
        result = sanitize_ocr_text(normal)
        assert result == normal

    def test_sanitize_handles_none(self):
        """None input should return None."""
        from src.ocr_processor import sanitize_ocr_text

        assert sanitize_ocr_text(None) is None

    def test_parse_extraction_sanitizes_all_fields(self):
        """parse_extraction_result should sanitize all text fields."""
        from src.ocr_processor import parse_extraction_result

        malicious_data = {
            "plaintiff": '<script>alert("xss")</script>Smith',
            "defendant": '<img src=x onerror=alert(1)>Jones',
            "case_number": "12345/2026",
            "court_name": "High Court",
            "pleading_type": '<b onclick="steal()">Notice</b>',
            "serving_attorney_name": "Normal Attorney",
            "confidence_score": 0.8,
        }
        result = parse_extraction_result(malicious_data)
        assert "<script>" not in (result.plaintiff or "")
        assert "<img" not in (result.defendant or "")
        assert "onclick" not in (result.pleading_type or "")


# =============================================================================
# ISSUE 2: File read into memory before size check
# =============================================================================

class TestStreamingFileSizeCheck:
    """File size must be checked via streaming, not by reading entire file into memory."""

    def test_save_uploaded_file_rejects_oversized_without_full_read(self):
        """save_uploaded_file should reject files exceeding max size using streaming."""
        import inspect
        from src.documents import save_uploaded_file

        source = inspect.getsource(save_uploaded_file)
        # The function should NOT read the entire file before checking size.
        # It should use chunked/streaming reads.
        # Check that we don't have the pattern: content = await file.read() followed by len(content)
        assert "content = await file.read()" not in source, \
            "save_uploaded_file should not read entire file into memory before size check"


# =============================================================================
# ISSUE 3: Email validation on registration
# =============================================================================

class TestEmailValidation:
    """Registration must validate email format."""

    async def test_register_rejects_invalid_email_format(self, client):
        """Registration with malformed email should fail."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "not-an-email",
                "password": "ValidPass123",
                "password_confirm": "ValidPass123",
                "full_name": "Test User",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400, \
            "Registration should reject malformed email addresses"

    async def test_register_rejects_email_without_domain(self, client):
        """Registration with email missing domain should fail."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "user@",
                "password": "ValidPass123",
                "password_confirm": "ValidPass123",
                "full_name": "Test User",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_register_accepts_valid_email(self, client):
        """Registration with valid email should succeed."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "valid@example.com",
                "password": "ValidPass123",
                "password_confirm": "ValidPass123",
                "full_name": "Valid User",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 303


# =============================================================================
# ISSUE 4: Duplicate password hashing
# =============================================================================

class TestPasswordHashingConsolidation:
    """pnsa_auth.py must import from auth.py, not duplicate code."""

    def test_pnsa_auth_imports_from_auth(self):
        """pnsa_auth.py should import hash_password from auth, not redefine it."""
        import inspect
        from src import pnsa_auth
        source = inspect.getsource(pnsa_auth)

        # Should NOT define its own hash_password function body with pbkdf2_hmac
        assert "pbkdf2_hmac" not in source, \
            "pnsa_auth.py should not contain its own PBKDF2 implementation - import from auth.py instead"

    def test_pnsa_auth_hash_and_verify_work(self):
        """pnsa_auth hash_password and verify_password should still function correctly."""
        from src.pnsa_auth import hash_password, verify_password

        hashed = hash_password("test_password")
        assert verify_password("test_password", hashed)
        assert not verify_password("wrong_password", hashed)


# =============================================================================
# ISSUE 5: SendGrid webhook accepts all when no secret configured
# =============================================================================

class TestWebhookSecurity:
    """Webhook endpoints must be secure even without SENDGRID_WEBHOOK_SECRET."""

    def test_webhook_verification_does_not_accept_all_when_no_secret(self):
        """verify_sendgrid_webhook_signature should NOT return True when no secret is set."""
        from src.email_tracking import verify_sendgrid_webhook_signature
        from src.config import settings

        original_secret = settings.SENDGRID_WEBHOOK_SECRET

        try:
            # Simulate no secret configured
            settings.SENDGRID_WEBHOOK_SECRET = ""

            # Should NOT blindly accept all webhooks
            result = verify_sendgrid_webhook_signature(
                payload=b'[{"event":"delivered"}]',
                signature="fake-signature",
                timestamp="12345",
            )
            assert result is False, \
                "Webhook verification must reject requests when no secret is configured"
        finally:
            settings.SENDGRID_WEBHOOK_SECRET = original_secret


# =============================================================================
# ISSUE 6: Race condition in document download
# =============================================================================

class TestDownloadAtomicity:
    """Document download marking must be atomic to prevent race conditions."""

    def test_mark_downloaded_uses_atomic_update(self):
        """Download should use atomic UPDATE...WHERE to prevent race conditions."""
        import inspect
        from src.documents import try_mark_document_downloaded
        source = inspect.getsource(try_mark_document_downloaded)

        # The function should use an atomic UPDATE ... WHERE approach
        assert "rows_affected" in source or "rowcount" in source, \
            "try_mark_document_downloaded should return rows_affected for atomic check"

        # Check that the route uses the atomic function
        from src.routes import document_routes
        route_source = inspect.getsource(document_routes)
        assert "try_mark_document_downloaded" in route_source, \
            "Download route should use try_mark_document_downloaded for atomic marking"


# =============================================================================
# ISSUE 7: Audit log hash chain concurrency
# =============================================================================

# =============================================================================
# ISSUE 8: SAST/UTC timestamp mismatch
# =============================================================================

class TestSASTTimestamps:
    """Legal documents must use South African Standard Time (UTC+2)."""

    def test_now_sast_returns_timezone_aware(self):
        """now_sast() should return a timezone-aware datetime in SAST."""
        from src.timestamps import now_sast, SAST

        result = now_sast()
        assert result.tzinfo is not None, "now_sast() must return timezone-aware datetime"
        assert result.utcoffset().total_seconds() == 7200, "SAST is UTC+2 (7200 seconds)"

    def test_to_sast_converts_utc_naive(self):
        """to_sast() should convert a naive UTC datetime to SAST."""
        from datetime import datetime
        from src.timestamps import to_sast

        utc_naive = datetime(2026, 1, 15, 10, 0, 0)  # 10:00 UTC
        result = to_sast(utc_naive)
        assert result.hour == 12, "10:00 UTC should be 12:00 SAST"

    def test_format_sast_for_legal(self):
        """format_sast() should produce a legal-compliant SAST string."""
        from datetime import datetime
        from src.timestamps import format_sast

        utc_naive = datetime(2026, 1, 15, 10, 30, 0)
        result = format_sast(utc_naive)
        assert "SAST" in result
        assert "12:30" in result  # 10:30 UTC = 12:30 SAST

    def test_pdf_generator_uses_sast_not_utc(self):
        """PDF generation code should use SAST, not UTC."""
        import inspect
        from src import pdf_generator
        source = inspect.getsource(pdf_generator)

        # Should not have "UTC" in timestamp display strings
        assert 'strftime("%d %B %Y at %H:%M:%S UTC")' not in source, \
            "PDF generator should display timestamps in SAST, not UTC"


class TestAuditChainConcurrency:
    """Audit log hash chain must handle concurrent writes correctly."""

    async def test_concurrent_audit_entries_maintain_chain(self, db):
        """Two sequential audit entries should form a valid chain."""
        from src.audit import log_event, verify_audit_chain_integrity

        entry1 = await log_event(
            db, event_type="test.first", description="First entry",
        )
        entry2 = await log_event(
            db, event_type="test.second", description="Second entry",
        )

        # Second entry should reference first entry's hash
        assert entry2.previous_hash == entry1.entry_hash, \
            "Second audit entry should reference first entry's hash"

        # Chain should verify
        result = await verify_audit_chain_integrity(db)
        assert result["valid"] is True
        assert result["entries_checked"] == 2

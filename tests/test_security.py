"""
Tests for security: CSRF protection, rate limiting, SECRET_KEY validation.

TDD: These tests define security requirements that MUST pass before deployment.
"""

import io

import pytest
from tests.conftest import csrf_data
from src.csrf import CSRF_COOKIE_NAME, generate_csrf_token
from src.rate_limit import rate_limit_store


# =============================================================================
# CSRF PROTECTION
# =============================================================================

class TestCSRFProtection:
    """All state-changing POST endpoints must require a valid CSRF token."""

    async def test_login_without_csrf_token_is_rejected(self, db):
        """POST /login without CSRF token should be rejected (403)."""
        from httpx import AsyncClient, ASGITransport
        from src.main import app
        from src.database import get_db

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as bare_client:
            response = await bare_client.post(
                "/login",
                data={
                    "email": "test@example.com",
                    "password": "TestPassword123",
                },
                follow_redirects=False,
            )
            assert response.status_code == 403
        app.dependency_overrides.clear()

    async def test_register_without_csrf_token_is_rejected(self, db):
        """POST /register without CSRF token should be rejected (403)."""
        from httpx import AsyncClient, ASGITransport
        from src.main import app
        from src.database import get_db

        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as bare_client:
            response = await bare_client.post(
                "/register",
                data={
                    "email": "csrftest@example.com",
                    "password": "ValidPass123",
                    "password_confirm": "ValidPass123",
                    "full_name": "CSRF Test",
                    "terms_accepted": "on",
                },
                follow_redirects=False,
            )
            assert response.status_code == 403
        app.dependency_overrides.clear()

    async def test_login_with_csrf_token_succeeds(self, client, test_user):
        """POST /login with valid CSRF token should work."""
        response = await client.post(
            "/login",
            data=csrf_data(client, {
                "email": "testuser@example.com",
                "password": "TestPassword123",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 303

    async def test_csrf_token_mismatch_rejected(self, client):
        """POST with mismatched CSRF token should be rejected."""
        response = await client.post(
            "/login",
            data={
                "csrf_token": "wrong-token-value",
                "email": "test@example.com",
                "password": "test",
            },
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_csrf_token_present_in_forms(self, client):
        """Login form should include a CSRF token hidden field."""
        response = await client.get("/login")
        assert response.status_code == 200
        assert "csrf_token" in response.text, \
            "Login form should contain a CSRF token field"


# =============================================================================
# RATE LIMITING
# =============================================================================

class TestRateLimiting:
    """Login and register endpoints must have rate limits."""

    async def test_login_rate_limited_after_many_attempts(self, client, test_user):
        """Login should be rate-limited after too many failed attempts."""
        rate_limit_store.reset()
        for i in range(11):
            await client.post(
                "/login",
                data=csrf_data(client, {
                    "email": "testuser@example.com",
                    "password": f"WrongPassword{i}",
                }),
                follow_redirects=False,
            )

        # After 10+ failed attempts, should get rate limited (429)
        response = await client.post(
            "/login",
            data=csrf_data(client, {
                "email": "testuser@example.com",
                "password": "WrongPasswordFinal",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 429, \
            "Login should be rate-limited after many failed attempts"
        rate_limit_store.reset()

    async def test_register_rate_limited(self, client):
        """Registration should be rate-limited."""
        rate_limit_store.reset()
        for i in range(11):
            await client.post(
                "/register",
                data=csrf_data(client, {
                    "email": f"ratelimit{i}@example.com",
                    "password": "ValidPass123",
                    "password_confirm": "ValidPass123",
                    "full_name": f"Rate Limit Test {i}",
                    "terms_accepted": "on",
                }),
                follow_redirects=False,
            )

        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "ratelimitfinal@example.com",
                "password": "ValidPass123",
                "password_confirm": "ValidPass123",
                "full_name": "Rate Limit Final",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 429, \
            "Registration should be rate-limited after many attempts"
        rate_limit_store.reset()


# =============================================================================
# SECRET KEY VALIDATION
# =============================================================================

class TestSecretKeyValidation:
    """Application must refuse to start with default SECRET_KEY in production."""

    def test_default_secret_key_rejected_in_production(self):
        """App should refuse to start with default key when DEBUG=False."""
        from pydantic import ValidationError
        from src.config import Settings

        # This should raise an error when DEBUG is False and key is default
        with pytest.raises((ValueError, ValidationError)):
            Settings(
                DEBUG=False,
                SECRET_KEY="dev-secret-key-change-in-production",
                DATABASE_URL="sqlite+aiosqlite:///:memory:",
                _env_file=None,  # Don't load .env
            )

    def test_custom_secret_key_accepted_in_production(self):
        """App should start fine with a custom key in production."""
        from src.config import Settings

        # Should NOT raise
        settings = Settings(
            DEBUG=False,
            SECRET_KEY="a-real-production-secret-key-that-is-long-enough",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            _env_file=None,
        )
        assert settings.SECRET_KEY == "a-real-production-secret-key-that-is-long-enough"

    def test_default_secret_key_allowed_in_debug(self):
        """Default key should be fine in debug mode."""
        from src.config import Settings

        # Should NOT raise in debug mode
        settings = Settings(
            DEBUG=True,
            SECRET_KEY="dev-secret-key-change-in-production",
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            _env_file=None,
        )
        assert settings.DEBUG is True


# =============================================================================
# HARDCODED SENDER_ID FIX
# =============================================================================

class TestPNSASenderID:
    """PNSA documents must not use hardcoded sender_id=1."""

    async def test_pnsa_document_does_not_use_hardcoded_sender(self, db, test_user):
        """PNSA document creation should use a proper system/service account, not hardcoded 1."""
        from src.models.document import Document

        # Verify the source code doesn't contain hardcoded sender_id=1
        import inspect
        from src.routes import pnsa_routes
        source = inspect.getsource(pnsa_routes)

        assert "sender_id=1" not in source, \
            "PNSA routes should not contain hardcoded sender_id=1"

    async def test_pnsa_walk_in_does_not_use_hardcoded_member_id(self, db):
        """Walk-in service should not use hardcoded billed_to_member_id=1."""
        import inspect
        from src.routes import pnsa_routes
        source = inspect.getsource(pnsa_routes)

        assert "billed_to_member_id=1" not in source, \
            "PNSA routes should not contain hardcoded billed_to_member_id=1"


# =============================================================================
# MISSING DEPENDENCY
# =============================================================================

class TestDependencies:
    """Required packages must be importable."""

    def test_pypdf_importable(self):
        """pypdf must be installed for PDF stamping functionality."""
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            pytest.fail("pypdf is not installed but is required by pdf_generator.py")

    def test_pdf_generator_importable(self):
        """pdf_generator module should import without errors."""
        try:
            from src.pdf_generator import generate_proof_of_service, generate_stamped_pdf
        except ImportError as e:
            pytest.fail(f"pdf_generator failed to import: {e}")

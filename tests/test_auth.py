"""
Tests for authentication: registration, login, logout, session management.

TDD: These tests define expected behavior for the auth system.
"""

import pytest
from src.auth import hash_password, verify_password, create_session_token, verify_session_token
from tests.conftest import csrf_data


# =============================================================================
# PASSWORD HASHING
# =============================================================================

class TestPasswordHashing:
    def test_hash_password_returns_salt_and_hash(self):
        """Hashed password should contain salt$hash format."""
        result = hash_password("mypassword")
        assert "$" in result
        salt, pwd_hash = result.split("$")
        assert len(salt) == 32  # 16 bytes = 32 hex chars
        assert len(pwd_hash) == 64  # SHA-256 = 64 hex chars

    def test_hash_password_produces_unique_salts(self):
        """Two hashes of the same password should have different salts."""
        hash1 = hash_password("samepassword")
        hash2 = hash_password("samepassword")
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Correct password should verify successfully."""
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_password_incorrect(self):
        """Wrong password should fail verification."""
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_malformed_hash(self):
        """Malformed hash string should not crash, just return False."""
        assert verify_password("anything", "not-a-valid-hash") is False
        assert verify_password("anything", "") is False


# =============================================================================
# SESSION TOKENS
# =============================================================================

class TestSessionTokens:
    def test_create_and_verify_session_token(self):
        """Valid token should decode back to original data."""
        token = create_session_token(42)
        data = verify_session_token(token)
        assert data is not None
        assert data["user_id"] == 42

    def test_expired_token_returns_none(self):
        """Expired token should return None."""
        import time
        token = create_session_token(42)
        # Wait then verify with very short max_age
        time.sleep(2)
        data = verify_session_token(token, max_age=1)
        assert data is None

    def test_tampered_token_returns_none(self):
        """Tampered token should return None."""
        token = create_session_token(42)
        tampered = token + "tampered"
        data = verify_session_token(tampered)
        assert data is None

    def test_garbage_token_returns_none(self):
        """Completely invalid token should return None."""
        data = verify_session_token("not-a-valid-token-at-all")
        assert data is None


# =============================================================================
# REGISTRATION (via HTTP)
# =============================================================================

class TestRegistration:
    async def test_register_page_loads(self, client):
        """Registration page should return 200."""
        response = await client.get("/register")
        assert response.status_code == 200

    async def test_register_new_user(self, client):
        """Valid registration should create user and redirect to dashboard."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "newuser@example.com",
                "password": "ValidPass123",
                "password_confirm": "ValidPass123",
                "full_name": "New User",
                "firm_name": "Test Firm",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/dashboard" in response.headers.get("location", "")

    async def test_register_duplicate_email(self, client, test_user):
        """Registering with existing email should fail with error."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "testuser@example.com",  # Already exists
                "password": "ValidPass123",
                "password_confirm": "ValidPass123",
                "full_name": "Duplicate User",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_register_password_mismatch(self, client):
        """Mismatched passwords should fail."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "mismatch@example.com",
                "password": "Password123",
                "password_confirm": "DifferentPass",
                "full_name": "User",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_register_short_password(self, client):
        """Password under 8 characters should fail."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "short@example.com",
                "password": "short",
                "password_confirm": "short",
                "full_name": "User",
                "terms_accepted": "on",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_register_without_terms(self, client):
        """Registration without accepting terms should fail."""
        response = await client.post(
            "/register",
            data=csrf_data(client, {
                "email": "noterms@example.com",
                "password": "ValidPass123",
                "password_confirm": "ValidPass123",
                "full_name": "User",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400


# =============================================================================
# LOGIN
# =============================================================================

class TestLogin:
    async def test_login_page_loads(self, client):
        """Login page should return 200."""
        response = await client.get("/login")
        assert response.status_code == 200

    async def test_login_valid_credentials(self, client, test_user):
        """Valid credentials should redirect and set session cookie."""
        response = await client.post(
            "/login",
            data=csrf_data(client, {
                "email": "testuser@example.com",
                "password": "TestPassword123",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "quickserve_session" in response.cookies

    async def test_login_invalid_password(self, client, test_user):
        """Wrong password should return 400 with error."""
        response = await client.post(
            "/login",
            data=csrf_data(client, {
                "email": "testuser@example.com",
                "password": "WrongPassword",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400

    async def test_login_nonexistent_user(self, client):
        """Nonexistent email should return 400."""
        response = await client.post(
            "/login",
            data=csrf_data(client, {
                "email": "nobody@example.com",
                "password": "AnyPassword123",
            }),
            follow_redirects=False,
        )
        assert response.status_code == 400


# =============================================================================
# LOGOUT
# =============================================================================

class TestLogout:
    async def test_logout_clears_session(self, auth_client):
        """Logout should clear the session cookie."""
        response = await auth_client.get("/logout", follow_redirects=False)
        assert response.status_code == 303
        # Cookie should be deleted (set to empty or max_age=0)
        assert "quickserve_session" in response.headers.get("set-cookie", "")


# =============================================================================
# PROTECTED ROUTES
# =============================================================================

class TestProtectedRoutes:
    async def test_dashboard_requires_auth(self, client):
        """Dashboard should redirect unauthenticated users to login."""
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers.get("location", "")

    async def test_dashboard_accessible_when_authenticated(self, auth_client):
        """Dashboard should return 200 for authenticated users."""
        response = await auth_client.get("/dashboard")
        assert response.status_code == 200

    async def test_upload_page_requires_auth(self, client):
        """Upload page should redirect unauthenticated users."""
        response = await client.get("/upload", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers.get("location", "")

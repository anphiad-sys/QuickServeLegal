"""
QuickServe Legal - Test Configuration and Fixtures

Provides async database sessions, test client, and helper fixtures
for all tests.
"""

import os
import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Set test environment BEFORE importing app code
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DEBUG"] = "true"
os.environ["UPLOAD_DIR"] = str(Path(__file__).parent / "test_uploads")
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASSWORD"] = ""

from src.database import Base, get_db
from src.main import app
from src.models import (
    User, Document, AuditLog, Certificate, Signature,
    Branch, BranchOperator, WalkInService,
)
from src.auth import hash_password
from src.csrf import CSRF_COOKIE_NAME, CSRF_FORM_FIELD, generate_csrf_token
from src.rate_limit import rate_limit_store


# Test database engine (in-memory SQLite)
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
)
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    """Provide a test database session with fresh tables for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db):
    """Provide an async HTTP test client with the test database and CSRF token."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    rate_limit_store.reset()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Pre-set a CSRF cookie so POST requests can include the matching token
        csrf_token = generate_csrf_token()
        ac.cookies.set(CSRF_COOKIE_NAME, csrf_token)
        # Store the token on the client for tests to include in form data
        ac._csrf_token = csrf_token
        yield ac

    app.dependency_overrides.clear()
    rate_limit_store.reset()


@pytest_asyncio.fixture
async def test_user(db):
    """Create a test user in the database."""
    user = User(
        email="testuser@example.com",
        password_hash=hash_password("TestPassword123"),
        full_name="Test User",
        firm_name="Test Law Firm",
        is_active=True,
        is_verified=True,
        email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_client(client, test_user):
    """Provide an authenticated test client (logged in as test_user)."""
    response = await client.post(
        "/login",
        data=csrf_data(client, {
            "email": "testuser@example.com",
            "password": "TestPassword123",
            "next": "/dashboard",
        }),
        follow_redirects=False,
    )
    # Extract session cookie from response
    cookies = response.cookies
    for name, value in cookies.items():
        client.cookies.set(name, value)
    return client


@pytest.fixture
def upload_dir(tmp_path):
    """Provide a temporary upload directory."""
    upload_path = tmp_path / "uploads"
    upload_path.mkdir()
    return upload_path


def csrf_data(client, extra_data=None):
    """Build form data dict including the CSRF token for the given client."""
    data = {CSRF_FORM_FIELD: client._csrf_token}
    if extra_data:
        data.update(extra_data)
    return data

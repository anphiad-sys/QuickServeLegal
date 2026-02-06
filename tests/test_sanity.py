"""Sanity check that the test infrastructure works."""

import pytest


async def test_db_fixture_works(db):
    """Verify the test database session is functional."""
    from sqlalchemy import text
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_client_fixture_works(client):
    """Verify the test HTTP client can hit the health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

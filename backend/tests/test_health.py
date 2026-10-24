"""Tests for platform liveness and readiness health checks."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.main import app


def test_liveness(client: TestClient):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_healthy(client: TestClient):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["database"] == "connected"


def test_readiness_database_failure(client: TestClient):
    # Mock a database failure
    def broken_db():
        mock = MagicMock(spec=Session)
        mock.execute.side_effect = Exception("Database connection timeout")
        yield mock

    app.dependency_overrides[get_db] = broken_db
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
    finally:
        app.dependency_overrides.clear()

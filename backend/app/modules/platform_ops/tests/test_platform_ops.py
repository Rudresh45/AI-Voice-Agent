"""Tests for platform ops domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import OutboxEvent, Tenant


def test_platform_ops_health(client: TestClient):
    resp = client.get("/api/v1/platform-ops/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["latency_ms"] >= 0


def test_platform_ops_stats(client: TestClient, db_session: Session):
    # Create test tenant
    tenant = Tenant(name="Stats Inc", slug="stats-inc")
    db_session.add(tenant)
    db_session.commit()

    resp = client.get("/api/v1/platform-ops/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tenants"] >= 1
    assert "total_agents" in data
    assert "total_conversations" in data


def test_platform_ops_outbox_pending(client: TestClient, db_session: Session):
    event = OutboxEvent(
        event_type="test.event",
        aggregate_type="agent",
        aggregate_id="agent-xyz",
        payload={"msg": "hello"},
        published=False,
    )
    db_session.add(event)
    db_session.commit()

    resp = client.get("/api/v1/platform-ops/outbox/pending")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    item = next(e for e in data if e["id"] == str(event.id))
    assert item["event_type"] == "test.event"
    assert item["published"] is False

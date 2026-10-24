"""Tests for audit domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, User
from app.modules.audit.service import AuditService


def test_list_audit_events_with_tenant_isolation(client: TestClient, db_session: Session):
    # Setup Tenant 1 and user
    t1 = Tenant(name="Audit Alpha", slug="audit-alpha")
    u1 = User(external_id="idp|audit_user1", email="audit1@test.com")
    db_session.add_all([t1, u1])
    db_session.commit()

    m1 = Membership(tenant_id=t1.id, user_id=u1.id, role="owner")
    db_session.add(m1)
    db_session.commit()

    # Setup Tenant 2 and user
    t2 = Tenant(name="Audit Beta", slug="audit-beta")
    u2 = User(external_id="idp|audit_user2", email="audit2@test.com")
    db_session.add_all([t2, u2])
    db_session.commit()

    m2 = Membership(tenant_id=t2.id, user_id=u2.id, role="owner")
    db_session.add(m2)
    db_session.commit()

    # Log audit events for t1
    audit_service = AuditService(db_session)
    audit_service.log_action(
        tenant_id=t1.id,
        actor_id=str(u1.id),
        action="agent.create",
        entity_type="agent",
        entity_id="ag-123",
        outcome="success",
        details={"name": "Sales Rep"},
        ip_address="127.0.0.1",
    )
    audit_service.log_action(
        tenant_id=t1.id,
        actor_id=str(u1.id),
        action="agent.update",
        entity_type="agent",
        entity_id="ag-123",
        outcome="success",
        details={"prompt": "Updated system prompt"},
    )

    # Log audit event for t2
    audit_service.log_action(
        tenant_id=t2.id,
        actor_id=str(u2.id),
        action="agent.delete",
        entity_type="agent",
        entity_id="ag-999",
        outcome="success",
        details={},
    )

    # Query audit logs for Tenant 1
    headers1 = {"X-User-ID": str(u1.id), "X-Tenant-ID": str(t1.id)}
    resp1 = client.get("/api/v1/audit/?page=1&per_page=10", headers=headers1)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["meta"]["total"] == 2
    assert len(data1["data"]) == 2
    assert all(item["tenant_id"] == str(t1.id) for item in data1["data"])
    assert data1["data"][0]["action"] == "agent.update"  # Most recent first

    # Query audit logs for Tenant 2
    headers2 = {"X-User-ID": str(u2.id), "X-Tenant-ID": str(t2.id)}
    resp2 = client.get("/api/v1/audit/?page=1&per_page=10", headers=headers2)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["meta"]["total"] == 1
    assert data2["data"][0]["action"] == "agent.delete"
    assert data2["data"][0]["tenant_id"] == str(t2.id)

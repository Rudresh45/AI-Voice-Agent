"""Tests for integrations domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, User


def test_tool_definition_lifecycle(client: TestClient, db_session: Session):
    tenant = Tenant(name="Integration Org", slug="integration-org")
    user = User(external_id="idp|integ_user", email="integ@test.com")
    db_session.add_all([tenant, user])
    db_session.commit()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="admin")
    db_session.add(membership)
    db_session.commit()

    headers = {"X-User-ID": str(user.id), "X-Tenant-ID": str(tenant.id)}

    # 1. Create custom tool
    create_resp = client.post(
        "/api/v1/integrations/tools",
        headers=headers,
        json={
            "name": "fetch_shipping_status",
            "description": "Check order tracking code.",
            "parameters_schema": {"type": "object", "properties": {"tracking_code": {"type": "string"}}},
            "requires_confirmation": True,
        },
    )
    assert create_resp.status_code == 201
    tool_id = create_resp.json()["id"]

    # 2. Get tool
    get_resp = client.get(f"/api/v1/integrations/tools/{tool_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "fetch_shipping_status"
    assert get_resp.json()["requires_confirmation"] is True

    # 3. List tools
    list_resp = client.get("/api/v1/integrations/tools", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

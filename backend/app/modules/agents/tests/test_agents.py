"""Tests for agents domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, ToolDefinition, User


def test_agent_crud_and_tool_assignment(client: TestClient, db_session: Session):
    tenant = Tenant(name="Agent Corp", slug="agent-corp")
    user = User(external_id="idp|agent_dev", email="agent_dev@test.com")
    db_session.add_all([tenant, user])
    db_session.commit()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db_session.add(membership)

    tool = ToolDefinition(
        tenant_id=None,
        name="calculator",
        description="Math operations",
        parameters_schema={"type": "object"},
    )
    db_session.add(tool)
    db_session.commit()

    headers = {"X-User-ID": str(user.id), "X-Tenant-ID": str(tenant.id)}

    # 1. Create agent
    create_resp = client.post(
        "/api/v1/agents/",
        headers=headers,
        json={
            "name": "Math Assistant",
            "instructions": "Help with calculations.",
            "tool_ids": [str(tool.id)],
        },
    )
    assert create_resp.status_code == 201
    agent_data = create_resp.json()
    agent_id = agent_data["id"]
    assert agent_data["name"] == "Math Assistant"
    assert len(agent_data["agent_tools"]) == 1

    # 2. Get agent
    get_resp = client.get(f"/api/v1/agents/{agent_id}", headers=headers)
    assert get_resp.status_code == 200

    # 3. List agents (paginated)
    list_resp = client.get("/api/v1/agents/", headers=headers)
    assert list_resp.status_code == 200
    page_data = list_resp.json()
    assert page_data["meta"]["total"] == 1
    assert page_data["data"][0]["name"] == "Math Assistant"

    # 4. Update agent
    patch_resp = client.patch(
        f"/api/v1/agents/{agent_id}",
        headers=headers,
        json={"name": "Math Assistant v2"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Math Assistant v2"

    # 5. Delete agent
    del_resp = client.delete(f"/api/v1/agents/{agent_id}", headers=headers)
    assert del_resp.status_code == 204

    # Verify deleted
    assert client.get(f"/api/v1/agents/{agent_id}", headers=headers).status_code == 404

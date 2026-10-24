"""Tests for conversations domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Agent, Membership, Tenant, User


def test_conversation_lifecycle_and_turns(client: TestClient, db_session: Session):
    tenant = Tenant(name="Chat Corp", slug="chat-corp")
    user = User(external_id="idp|caller_1", email="caller@test.com")
    agent = Agent(tenant_id=tenant.id, name="Chat Assistant", instructions="Assist callers.")
    db_session.add_all([tenant, user, agent])
    db_session.commit()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="member")
    db_session.add(membership)
    db_session.commit()

    headers = {"X-User-ID": str(user.id), "X-Tenant-ID": str(tenant.id)}

    # 1. Create conversation
    create_resp = client.post(
        "/api/v1/conversations/",
        headers=headers,
        json={"agent_id": str(agent.id), "title": "Customer Help Session"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # 2. Add user turn
    user_turn = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"role": "user", "content": "How do I update my profile?", "token_count": 8},
    )
    assert user_turn.status_code == 201
    assert user_turn.json()["role"] == "user"

    # 3. Add assistant turn
    asst_turn = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        headers=headers,
        json={"role": "assistant", "content": "Navigate to settings to update.", "token_count": 7},
    )
    assert asst_turn.status_code == 201

    # 4. List messages
    msg_list = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assert msg_list.status_code == 200
    msgs = msg_list.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"

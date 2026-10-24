"""Tests verifying SQLAlchemy relationships and cascade deletion policies."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    AgentTool,
    Conversation,
    Message,
    Tenant,
    ToolDefinition,
    User,
)


def test_tenant_cascade_delete(db_session: Session):
    """Deleting a Tenant must cascade and delete its agents, conversations, and messages."""
    tenant = Tenant(name="Cascade Corp", slug="cascade-corp")
    db_session.add(tenant)
    db_session.flush()

    user = User(external_id="ext_cascade", email="cascade@test.com")
    db_session.add(user)
    db_session.flush()

    agent = Agent(tenant_id=tenant.id, name="Bot", instructions="Test")
    db_session.add(agent)
    db_session.flush()

    conv = Conversation(tenant_id=tenant.id, agent_id=agent.id, user_id=user.id)
    db_session.add(conv)
    db_session.flush()

    msg = Message(tenant_id=tenant.id, conversation_id=conv.id, role="user", content="Hi")
    db_session.add(msg)
    db_session.flush()

    conv_id = conv.id
    agent_id = agent.id
    msg_id = msg.id

    # Delete tenant
    db_session.delete(tenant)
    db_session.flush()
    db_session.expire_all()

    # Verify children were cascaded
    assert db_session.get(Agent, agent_id) is None
    assert db_session.get(Conversation, conv_id) is None
    assert db_session.get(Message, msg_id) is None
    # User should NOT be deleted (global identity)
    assert db_session.get(User, user.id) is not None


def test_tool_delete_restricted_when_in_use(db_session: Session):
    """Deleting a ToolDefinition referenced by an AgentTool must be restricted."""
    tenant = Tenant(name="Restrict Corp", slug="restrict-corp")
    agent = Agent(tenant_id=tenant.id, name="Tool Bot", instructions="Test")
    tool = ToolDefinition(name="locked_tool", description="Critical tool", parameters_schema={})
    db_session.add_all([tenant, agent, tool])
    db_session.flush()

    agent_tool = AgentTool(tenant_id=tenant.id, agent_id=agent.id, tool_id=tool.id)
    db_session.add(agent_tool)
    db_session.flush()

    # Attempting to delete tool directly while referenced by agent_tool
    db_session.delete(tool)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_conversation_messages_ordering(db_session: Session):
    """Messages on a conversation should be ordered chronologically."""
    tenant = Tenant(name="Order Corp", slug="order-corp")
    agent = Agent(tenant_id=tenant.id, name="Order Bot", instructions="Test")
    db_session.add_all([tenant, agent])
    db_session.flush()

    conv = Conversation(tenant_id=tenant.id, agent_id=agent.id)
    db_session.add(conv)
    db_session.flush()

    msg1 = Message(tenant_id=tenant.id, conversation_id=conv.id, role="user", content="First")
    msg2 = Message(tenant_id=tenant.id, conversation_id=conv.id, role="assistant", content="Second")
    msg3 = Message(tenant_id=tenant.id, conversation_id=conv.id, role="user", content="Third")
    db_session.add_all([msg1, msg2, msg3])
    db_session.flush()

    # Refresh conversation
    refreshed_conv = db_session.get(Conversation, conv.id)
    assert refreshed_conv is not None
    assert [m.content for m in refreshed_conv.messages] == ["First", "Second", "Third"]

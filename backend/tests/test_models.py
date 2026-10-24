"""Tests for model creation, retrieval, UUIDs, and UTC timestamps across all 13 entities."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    AgentStatus,
    AgentTool,
    AuditEvent,
    AuditOutcome,
    Conversation,
    ConversationStatus,
    KnowledgeDocument,
    Membership,
    MembershipRole,
    Message,
    MessageRole,
    OutboxEvent,
    Tenant,
    TenantStatus,
    ToolDefinition,
    ToolExecution,
    ToolExecutionStatus,
    UsageEvent,
    User,
)


def test_create_and_retrieve_all_entities(db_session: Session):
    """Verify each of the 13 required entities can be instantiated and persisted."""

    # 1. Tenant
    tenant = Tenant(name="Test Org", slug="test-org", status=TenantStatus.ACTIVE.value)
    db_session.add(tenant)
    db_session.flush()
    assert isinstance(tenant.id, uuid.UUID)
    assert tenant.created_at.tzinfo is not None

    # 2. User
    user = User(
        external_id="idp|test_user_1",
        email="user@test.org",
        display_name="Test User",
    )
    db_session.add(user)
    db_session.flush()
    assert isinstance(user.id, uuid.UUID)
    assert user.is_active is True

    # 3. Membership
    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role=MembershipRole.OWNER.value,
    )
    db_session.add(membership)
    db_session.flush()
    assert membership.role == MembershipRole.OWNER.value

    # 4. Agent
    agent = Agent(
        tenant_id=tenant.id,
        name="Support Agent",
        instructions="Help users accurately.",
        model_id="gemini-2.5-flash",
        model_config_json={"temperature": 0.3},
        status=AgentStatus.ACTIVE.value,
    )
    db_session.add(agent)
    db_session.flush()
    assert agent.name == "Support Agent"
    assert agent.model_config_json["temperature"] == 0.3

    # 5. ToolDefinition
    tool = ToolDefinition(
        tenant_id=None,
        name="calculator",
        description="Calculates expressions.",
        parameters_schema={"type": "object", "properties": {"expr": {"type": "string"}}},
        requires_confirmation=False,
    )
    db_session.add(tool)
    db_session.flush()
    assert tool.requires_confirmation is False

    # 6. AgentTool
    agent_tool = AgentTool(
        tenant_id=tenant.id,
        agent_id=agent.id,
        tool_id=tool.id,
        permission_level="standard",
    )
    db_session.add(agent_tool)
    db_session.flush()
    assert agent_tool.is_enabled is True

    # 7. Conversation
    conversation = Conversation(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        title="Session 1",
        status=ConversationStatus.ACTIVE.value,
    )
    db_session.add(conversation)
    db_session.flush()
    assert conversation.status == ConversationStatus.ACTIVE.value

    # 8. Message
    msg = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        role=MessageRole.USER.value,
        content="Hello world",
        token_count=3,
        meta_data={"source": "mic"},
    )
    db_session.add(msg)
    db_session.flush()
    assert msg.content == "Hello world"

    # 9. ToolExecution
    execution = ToolExecution(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        tool_id=tool.id,
        tool_name="calculator",
        idempotency_key="idemp_101",
        arguments_json={"expr": "2+2"},
        result_json={"result": 4},
        status=ToolExecutionStatus.COMPLETED.value,
        duration_ms=12,
    )
    db_session.add(execution)
    db_session.flush()
    assert execution.status == ToolExecutionStatus.COMPLETED.value

    # 10. KnowledgeDocument
    doc = KnowledgeDocument(
        tenant_id=tenant.id,
        title="Manual",
        storage_key="s3://bucket/manual.pdf",
        content_type="application/pdf",
        byte_size=2048,
        checksum_sha256="abcd1234ef",
        ingestion_status="completed",
        meta_data={},
    )
    db_session.add(doc)
    db_session.flush()
    assert doc.byte_size == 2048

    # 11. UsageEvent
    usage = UsageEvent(
        tenant_id=tenant.id,
        event_type="gemini_tokens",
        quantity=50,
        unit="tokens",
    )
    db_session.add(usage)
    db_session.flush()
    assert usage.quantity == 50

    # 12. AuditEvent
    audit = AuditEvent(
        tenant_id=tenant.id,
        actor_id=str(user.id),
        action="agent.invoke",
        entity_type="Agent",
        entity_id=str(agent.id),
        outcome=AuditOutcome.SUCCESS.value,
        details={"tokens": 50},
    )
    db_session.add(audit)
    db_session.flush()
    assert audit.outcome == AuditOutcome.SUCCESS.value

    # 13. OutboxEvent
    outbox = OutboxEvent(
        event_type="agent.invoked",
        aggregate_type="Agent",
        aggregate_id=str(agent.id),
        payload={"agent_id": str(agent.id)},
    )
    db_session.add(outbox)
    db_session.flush()
    assert outbox.published is False

    # Verify query retrieval
    saved_tenant = db_session.scalars(select(Tenant).where(Tenant.id == tenant.id)).one()
    assert saved_tenant.name == "Test Org"
    assert len(saved_tenant.memberships) == 1
    assert len(saved_tenant.agents) == 1

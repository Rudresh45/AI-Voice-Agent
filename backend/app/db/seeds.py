"""Development-only seed data.

Strict Security Rule:
- Synthetic demonstration data ONLY.
- Zero real customer data, personal identifiers, or production API keys.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.security import hash_password
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


def seed_development_data(db: Session) -> dict[str, Any]:
    """Populate an empty database with realistic, isolated development records."""
    # 1. Tenants
    tenant_acme = Tenant(
        name="Acme Corporation",
        slug="acme-corp",
        status=TenantStatus.ACTIVE.value,
    )
    tenant_beta = Tenant(
        name="Beta Logistics",
        slug="beta-logistics",
        status=TenantStatus.ACTIVE.value,
    )
    db.add_all([tenant_acme, tenant_beta])
    db.flush()

    # 2. Users (Global identity references with synthetic data)
    dev_password_hash = hash_password("DevPassword123!")
    user_alice = User(
        external_id="auth0|dev_alice_001",
        email="alice.developer@example.internal",
        display_name="Alice (Dev Admin)",
        hashed_password=dev_password_hash,
        is_platform_admin=True,
    )
    user_bob = User(
        external_id="auth0|dev_bob_002",
        email="bob.tester@example.internal",
        display_name="Bob (Dev Member)",
        hashed_password=dev_password_hash,
    )
    db.add_all([user_alice, user_bob])
    db.flush()

    # 3. Memberships
    membership_alice = Membership(
        tenant_id=tenant_acme.id,
        user_id=user_alice.id,
        role=MembershipRole.OWNER.value,
    )
    membership_bob = Membership(
        tenant_id=tenant_acme.id,
        user_id=user_bob.id,
        role=MembershipRole.MEMBER.value,
    )
    db.add_all([membership_alice, membership_bob])
    db.flush()

    # 4. Tool Definitions (System tool + Tenant custom tool)
    tool_weather = ToolDefinition(
        tenant_id=None,  # System standard tool
        name="lookup_weather",
        description="Retrieves current weather forecast for a given latitude and longitude.",
        parameters_schema={
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
            },
            "required": ["latitude", "longitude"],
        },
        requires_confirmation=False,
    )
    tool_acme_crm = ToolDefinition(
        tenant_id=tenant_acme.id,  # Custom tenant tool
        name="query_acme_inventory",
        description="Check product availability in Acme Corp internal catalog.",
        parameters_schema={
            "type": "object",
            "properties": {"sku": {"type": "string"}},
            "required": ["sku"],
        },
        requires_confirmation=False,
    )
    db.add_all([tool_weather, tool_acme_crm])
    db.flush()

    # 5. Agents
    agent_support = Agent(
        tenant_id=tenant_acme.id,
        name="Customer Support Voice Agent",
        description="Friendly automated voice assistant for Acme inquiries.",
        instructions="Assist callers with inventory status and weather updates concisely.",
        model_id="gemini-2.5-flash",
        model_config_json={"temperature": 0.2, "max_output_tokens": 512},
        status=AgentStatus.ACTIVE.value,
    )
    db.add(agent_support)
    db.flush()

    # 6. Assign Tools to Agent
    agent_tool_1 = AgentTool(
        tenant_id=tenant_acme.id,
        agent_id=agent_support.id,
        tool_id=tool_weather.id,
        permission_level="standard",
    )
    agent_tool_2 = AgentTool(
        tenant_id=tenant_acme.id,
        agent_id=agent_support.id,
        tool_id=tool_acme_crm.id,
        permission_level="standard",
    )
    db.add_all([agent_tool_1, agent_tool_2])
    db.flush()

    # 7. Sample Conversation & Messages
    conv = Conversation(
        tenant_id=tenant_acme.id,
        agent_id=agent_support.id,
        user_id=user_alice.id,
        title="Sample Call Session #1",
        status=ConversationStatus.ACTIVE.value,
    )
    db.add(conv)
    db.flush()

    msg_user = Message(
        tenant_id=tenant_acme.id,
        conversation_id=conv.id,
        role=MessageRole.USER.value,
        content="Hello, is widget SKU-1042 in stock?",
        token_count=12,
    )
    msg_agent = Message(
        tenant_id=tenant_acme.id,
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT.value,
        content="Checking inventory for SKU-1042 now.",
        token_count=10,
    )
    db.add_all([msg_user, msg_agent])
    db.flush()

    # 8. Sample Tool Execution
    tool_exec = ToolExecution(
        tenant_id=tenant_acme.id,
        conversation_id=conv.id,
        tool_id=tool_acme_crm.id,
        tool_name="query_acme_inventory",
        idempotency_key="idemp_seed_test_001",
        arguments_json={"sku": "SKU-1042"},
        result_json={"in_stock": True, "quantity": 140},
        status=ToolExecutionStatus.COMPLETED.value,
        duration_ms=45,
    )
    db.add(tool_exec)
    db.flush()

    # 9. Knowledge Document Reference
    doc = KnowledgeDocument(
        tenant_id=tenant_acme.id,
        title="Acme Shipping Guidelines 2026",
        storage_key="tenants/acme/docs/shipping-2026.pdf",
        content_type="application/pdf",
        byte_size=1048576,
        checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ingestion_status="completed",
        meta_data={"category": "operations"},
    )
    db.add(doc)

    # 10. Usage Event
    usage = UsageEvent(
        tenant_id=tenant_acme.id,
        event_type="gemini_tokens",
        quantity=22,
        unit="tokens",
        meta_data={"model": "gemini-2.5-flash"},
    )
    db.add(usage)

    # 11. Audit Event
    audit = AuditEvent(
        tenant_id=tenant_acme.id,
        actor_id=str(user_alice.id),
        action="agent.create",
        entity_type="Agent",
        entity_id=str(agent_support.id),
        outcome=AuditOutcome.SUCCESS.value,
        details={"agent_name": agent_support.name},
    )
    db.add(audit)

    # 12. Outbox Event
    outbox = OutboxEvent(
        event_type="conversation.created",
        aggregate_type="Conversation",
        aggregate_id=str(conv.id),
        payload={"tenant_id": str(tenant_acme.id), "title": conv.title},
        published=False,
    )
    db.add(outbox)
    db.commit()

    return {
        "tenant_id": tenant_acme.id,
        "other_tenant_id": tenant_beta.id,
        "user_id": user_alice.id,
        "agent_id": agent_support.id,
        "conversation_id": conv.id,
    }

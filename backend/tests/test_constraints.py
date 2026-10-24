"""Tests verifying database uniqueness constraints and foreign key rejections."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    Conversation,
    Membership,
    Tenant,
    ToolExecution,
    User,
)


def test_tenant_name_uniqueness(db_session: Session):
    """Duplicate tenant name must be rejected."""
    t1 = Tenant(name="Alpha Org", slug="alpha-org-1")
    db_session.add(t1)
    db_session.flush()

    t2 = Tenant(name="Alpha Org", slug="alpha-org-2")
    db_session.add(t2)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_tenant_slug_uniqueness(db_session: Session):
    """Duplicate tenant slug must be rejected."""
    t1 = Tenant(name="Alpha Org 1", slug="alpha-org")
    db_session.add(t1)
    db_session.flush()

    t2 = Tenant(name="Alpha Org 2", slug="alpha-org")
    db_session.add(t2)
    with pytest.raises(IntegrityError):
        db_session.flush()



def test_membership_tenant_user_uniqueness(db_session: Session):
    """A user cannot have duplicate memberships within the same tenant."""
    tenant = Tenant(name="Membership Org", slug="membership-org")
    user = User(external_id="ext_member", email="member@test.com")
    db_session.add_all([tenant, user])
    db_session.flush()

    m1 = Membership(tenant_id=tenant.id, user_id=user.id, role="member")
    db_session.add(m1)
    db_session.flush()

    # Duplicate membership
    m2 = Membership(tenant_id=tenant.id, user_id=user.id, role="admin")
    db_session.add(m2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_agent_name_unique_within_same_tenant(db_session: Session):
    """Agent names must be unique within a single tenant."""
    t1 = Tenant(name="Tenant 1", slug="tenant-1")
    db_session.add(t1)
    db_session.flush()

    a1 = Agent(tenant_id=t1.id, name="Sales Bot", instructions="Sell")
    db_session.add(a1)
    db_session.flush()

    a2 = Agent(tenant_id=t1.id, name="Sales Bot", instructions="Other instructions")
    db_session.add(a2)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_agent_name_allowed_across_different_tenants(db_session: Session):
    """Same agent name can exist across different tenants."""
    t1 = Tenant(name="Tenant A", slug="tenant-a")
    t2 = Tenant(name="Tenant B", slug="tenant-b")
    db_session.add_all([t1, t2])
    db_session.flush()

    a1 = Agent(tenant_id=t1.id, name="Sales Bot", instructions="Sell in A")
    a2 = Agent(tenant_id=t2.id, name="Sales Bot", instructions="Sell in B")
    db_session.add_all([a1, a2])
    db_session.flush()

    assert a1.id != a2.id
    assert a1.name == a2.name



def test_foreign_key_violation_rejected(db_session: Session):
    """Records referencing non-existent foreign keys must be rejected."""
    fake_tenant_id = uuid.uuid4()
    agent = Agent(tenant_id=fake_tenant_id, name="Ghost Agent", instructions="Ghost")
    db_session.add(agent)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_tool_execution_idempotency_key_unique_per_tenant(db_session: Session):
    """Tool executions within the same tenant cannot reuse an idempotency key."""
    tenant = Tenant(name="Idemp Org", slug="idemp-org")
    agent = Agent(tenant_id=tenant.id, name="Exec Bot", instructions="Test")
    db_session.add_all([tenant, agent])
    db_session.flush()

    conv = Conversation(tenant_id=tenant.id, agent_id=agent.id)
    db_session.add(conv)
    db_session.flush()

    e1 = ToolExecution(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        tool_name="stripe_charge",
        idempotency_key="pay_abc123",
        arguments_json={"amount": 100},
    )
    db_session.add(e1)
    db_session.flush()

    # Duplicate execution with same idempotency key in the same tenant
    e2 = ToolExecution(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        tool_name="stripe_charge",
        idempotency_key="pay_abc123",
        arguments_json={"amount": 100},
    )
    db_session.add(e2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

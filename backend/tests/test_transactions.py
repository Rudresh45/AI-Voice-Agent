"""Tests for atomic transactions, rollbacks, and the transactional outbox pattern."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Agent, Conversation, Tenant
from app.db.repositories.outbox import OutboxRepository


def test_transaction_rollback_on_failure(db_session: Session):
    """When a multi-step operation fails midway, all changes must be rolled back."""
    tenant = Tenant(name="Tx Corp", slug="tx-corp")
    db_session.add(tenant)
    db_session.flush()

    try:
        # Step 1: Add an agent
        agent = Agent(tenant_id=tenant.id, name="Valid Agent", instructions="Valid")
        db_session.add(agent)
        db_session.flush()

        # Step 2: Add an invalid agent (violating foreign key constraint)
        invalid_agent = Agent(
            tenant_id=uuid.uuid4(), name="Invalid Agent", instructions="Invalid"
        )
        db_session.add(invalid_agent)
        db_session.flush()
    except IntegrityError:
        db_session.rollback()

    # Verify that Step 1 was also rolled back
    agents = db_session.scalars(select(Agent).where(Agent.tenant_id == tenant.id)).all()
    assert len(agents) == 0


def test_transactional_outbox_pattern(db_session: Session):
    """Business record and outbox event must be persisted together atomically."""
    tenant = Tenant(name="Outbox Corp", slug="outbox-corp")
    agent = Agent(tenant_id=tenant.id, name="Outbox Bot", instructions="Test")
    db_session.add_all([tenant, agent])
    db_session.flush()

    outbox_repo = OutboxRepository(db_session)

    # Within one transaction: create conversation and record outbox event
    conv = Conversation(tenant_id=tenant.id, agent_id=agent.id, title="Outbox Conv")
    db_session.add(conv)
    db_session.flush()

    outbox_event = outbox_repo.record_event(
        event_type="conversation.created",
        aggregate_type="Conversation",
        aggregate_id=str(conv.id),
        payload={"tenant_id": str(tenant.id), "title": conv.title},
    )
    db_session.commit()

    # Query unpublished events
    pending = outbox_repo.list_unpublished()
    assert len(pending) >= 1
    target = next(e for e in pending if e.id == outbox_event.id)
    assert target.published is False
    assert target.aggregate_id == str(conv.id)

    # Mark as published
    outbox_repo.mark_published(target.id)
    db_session.commit()

    updated = outbox_repo.get_by_id(target.id)
    assert updated is not None
    assert updated.published is True
    assert updated.published_at is not None

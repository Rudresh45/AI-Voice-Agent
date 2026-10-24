"""Tests verifying seed data population in clean development databases."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, Conversation, Tenant, ToolDefinition, User
from app.db.seeds import seed_development_data


def test_seed_development_data(db_session: Session):
    """Verify that seed_development_data runs cleanly and populates all baseline records."""
    summary = seed_development_data(db_session)

    assert "tenant_id" in summary
    assert "agent_id" in summary
    assert "conversation_id" in summary

    # Verify entities exist in database
    tenants = db_session.scalars(select(Tenant)).all()
    assert len(tenants) == 2  # Acme and Beta Logistics

    users = db_session.scalars(select(User)).all()
    assert len(users) == 2

    agents = db_session.scalars(select(Agent)).all()
    assert len(agents) == 1
    assert agents[0].name == "Customer Support Voice Agent"

    tools = db_session.scalars(select(ToolDefinition)).all()
    assert len(tools) == 2  # System weather tool + Acme inventory tool

    conversations = db_session.scalars(select(Conversation)).all()
    assert len(conversations) == 1
    assert len(conversations[0].messages) == 2
    assert len(conversations[0].tool_executions) == 1

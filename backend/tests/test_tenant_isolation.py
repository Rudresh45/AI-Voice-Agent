"""Tests verifying cross-tenant isolation and security enforcement."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.models import Tenant
from app.db.repositories.agent import AgentRepository
from app.db.tenant_scope import TenantAccessDeniedError


def test_cross_tenant_access_denied(db_session: Session):
    """Attempting to access Tenant A's agent via Tenant B's credentials must raise TenantAccessDeniedError."""
    tenant_a = Tenant(name="Tenant Alpha", slug="tenant-alpha")
    tenant_b = Tenant(name="Tenant Beta", slug="tenant-beta")
    db_session.add_all([tenant_a, tenant_b])
    db_session.flush()

    repo = AgentRepository(db_session)
    agent_a = repo.create(
        tenant_id=tenant_a.id,
        name="Alpha Bot",
        instructions="Alpha only",
    )

    # 1. Tenant A can access its own agent
    found = repo.get_by_id_scoped(agent_a.id, tenant_a.id)
    assert found.id == agent_a.id

    # 2. Tenant B attempting to access Tenant A's agent triggers security violation
    with pytest.raises(TenantAccessDeniedError) as exc_info:
        repo.get_by_id_scoped(agent_a.id, tenant_b.id)

    assert exc_info.value.tenant_id == tenant_b.id
    assert exc_info.value.entity_name == "Agent"


def test_tenant_scoped_list_isolation(db_session: Session):
    """Listing agents for Tenant A must never return Tenant B's agents."""
    tenant_a = Tenant(name="Org A", slug="org-a")
    tenant_b = Tenant(name="Org B", slug="org-b")
    db_session.add_all([tenant_a, tenant_b])
    db_session.flush()

    repo = AgentRepository(db_session)
    repo.create(tenant_id=tenant_a.id, name="Agent A1", instructions="A1")
    repo.create(tenant_id=tenant_a.id, name="Agent A2", instructions="A2")
    repo.create(tenant_id=tenant_b.id, name="Agent B1", instructions="B1")

    agents_a = repo.list_scoped(tenant_a.id)
    assert len(agents_a) == 2
    assert {a.name for a in agents_a} == {"Agent A1", "Agent A2"}

    agents_b = repo.list_scoped(tenant_b.id)
    assert len(agents_b) == 1
    assert agents_b[0].name == "Agent B1"


def test_nonexistent_entity_raises_lookup_error(db_session: Session):
    """Accessing a completely non-existent entity raises LookupError, not TenantAccessDeniedError."""
    tenant = Tenant(name="Lookup Org", slug="lookup-org")
    db_session.add(tenant)
    db_session.flush()

    repo = AgentRepository(db_session)
    random_id = uuid.uuid4()
    with pytest.raises(LookupError):
        repo.get_by_id_scoped(random_id, tenant.id)

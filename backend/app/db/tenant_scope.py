"""Tenant isolation enforcement and scoping utilities.

Security Principle:
- Never trust a client-supplied tenant_id. Tenant context must be resolved
  from authenticated credentials (JWT, API key, or session context).
- Every query accessing tenant-owned entities MUST be scoped by tenant_id.
- Adding tenant_id alone does not guarantee isolation; repository methods and
  filters must explicitly verify tenant boundaries.
"""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Base

T = TypeVar("T", bound=Base)


class TenantAccessDeniedError(Exception):
    """Raised when an operation attempts to access cross-tenant data."""

    def __init__(self, tenant_id: uuid.UUID | str, entity_name: str, entity_id: Any):
        super().__init__(
            f"Tenant '{tenant_id}' is not authorized to access {entity_name} '{entity_id}'"
        )
        self.tenant_id = tenant_id
        self.entity_name = entity_name
        self.entity_id = entity_id


def scope_query_to_tenant[T: Base](stmt: Select[Any], model: type[T], tenant_id: uuid.UUID) -> Select[Any]:
    """Apply a strict tenant_id filter to a SQLAlchemy Select statement."""
    if not hasattr(model, "tenant_id"):
        raise AttributeError(f"Model '{model.__name__}' is not a tenant-scoped entity.")
    return stmt.where(model.tenant_id == tenant_id)


def verify_tenant_ownership[T: Base](
    db: Session,
    model: type[T],
    entity_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> T:
    """Fetch an entity by ID while strictly asserting tenant ownership.

    Raises:
        TenantAccessDeniedError: If the entity exists under a different tenant.
        LookupError: If the entity does not exist at all.
    """
    # First check if the entity exists under the requested tenant
    stmt = select(model).where(model.id == entity_id, model.tenant_id == tenant_id)
    entity = db.scalars(stmt).first()
    if entity is not None:
        return entity

    # Check if entity exists in another tenant (security violation detection)
    cross_tenant_stmt = select(model.id).where(model.id == entity_id)
    exists_elsewhere = db.scalars(cross_tenant_stmt).first() is not None
    if exists_elsewhere:
        raise TenantAccessDeniedError(tenant_id, model.__name__, entity_id)

    raise LookupError(f"{model.__name__} with ID '{entity_id}' not found.")

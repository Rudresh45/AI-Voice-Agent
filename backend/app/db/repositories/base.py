"""Generic Base Repository pattern for data access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Base
from app.db.tenant_scope import scope_query_to_tenant, verify_tenant_ownership

T = TypeVar("T", bound=Base)


class BaseRepository[T: Base]:
    """Generic repository providing standardized persistence operations."""

    def __init__(self, model: type[T], db: Session):
        self.model = model
        self.db = db

    def add(self, entity: T) -> T:
        """Add a new entity to the session."""
        self.db.add(entity)
        self.db.flush()
        return entity

    def get_by_id(self, entity_id: uuid.UUID) -> T | None:
        """Fetch an entity by primary key (for non-tenant entities)."""
        return self.db.get(self.model, entity_id)

    def delete(self, entity: T) -> None:
        """Mark an entity for deletion."""
        self.db.delete(entity)
        self.db.flush()


class TenantScopedRepository(BaseRepository[T]):
    """Repository enforcing tenant boundary checks on all queries and mutations."""

    def get_by_id_scoped(self, entity_id: uuid.UUID, tenant_id: uuid.UUID) -> T:
        """Fetch an entity asserting tenant isolation.

        Raises:
            TenantAccessDeniedError: If the entity belongs to another tenant.
            LookupError: If the entity does not exist.
        """
        return verify_tenant_ownership(self.db, self.model, entity_id, tenant_id)

    def get_by_id_or_none(self, entity_id: uuid.UUID, tenant_id: uuid.UUID) -> T | None:
        """Fetch an entity scoped to tenant, or None if not found in this tenant."""
        stmt = select(self.model).where(
            self.model.id == entity_id,  # type: ignore[attr-defined]
            self.model.tenant_id == tenant_id,  # type: ignore[attr-defined]
        )
        return self.db.scalars(stmt).first()

    def list_scoped(
        self,
        tenant_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[T]:
        """List entities belonging to the specified tenant."""
        stmt: Select[Any] = select(self.model)
        stmt = scope_query_to_tenant(stmt, self.model, tenant_id)
        stmt = stmt.offset(skip).limit(limit)
        return self.db.scalars(stmt).all()

    def delete_scoped(self, entity_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Delete an entity after verifying tenant ownership."""
        entity = self.get_by_id_scoped(entity_id, tenant_id)
        self.db.delete(entity)
        self.db.flush()

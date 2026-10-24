"""Tenants domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership
from app.db.repositories.tenant import MembershipRepository, TenantRepository


class TenantDomainRepository:
    """Aggregates tenant and membership database interactions."""

    def __init__(self, db: Session):
        self.db = db
        self.tenants = TenantRepository(db)
        self.memberships = MembershipRepository(db)

    def get_user_role(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        stmt = select(Membership.role).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
        return self.db.scalars(stmt).first()

    def list_members(self, tenant_id: uuid.UUID) -> Sequence[Membership]:
        return self.memberships.list_by_tenant(tenant_id)

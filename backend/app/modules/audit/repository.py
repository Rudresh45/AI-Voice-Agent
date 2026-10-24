"""Audit domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.db.models import AuditEvent
from app.db.repositories.audit import AuditRepository


class AuditDomainRepository(AuditRepository):
    """Domain-specific repository extending standard AuditRepository."""

    def count_by_tenant(self, tenant_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        return self.db.scalar(stmt) or 0

    def list_paginated(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Sequence[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

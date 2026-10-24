"""Knowledge domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument
from app.db.repositories.base import TenantScopedRepository


class KnowledgeRepository(TenantScopedRepository[KnowledgeDocument]):
    """Repository managing tenant documents and vectors."""

    def __init__(self, db: Session):
        super().__init__(KnowledgeDocument, db)

    def count_by_tenant(self, tenant_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id)
        )
        return self.db.scalar(stmt) or 0

    def list_paginated(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Sequence[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id)
            .order_by(KnowledgeDocument.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

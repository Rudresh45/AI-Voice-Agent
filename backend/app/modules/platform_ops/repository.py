"""Platform ops domain repository."""

from __future__ import annotations

import time
from collections.abc import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import Agent, Conversation, KnowledgeDocument, OutboxEvent, Tenant
from app.db.repositories.outbox import OutboxRepository


class PlatformOpsRepository:
    """Repository handling platform operations, stats and outbox polling."""

    def __init__(self, db: Session):
        self.db = db
        self.outbox_repo = OutboxRepository(db)

    def ping_db(self) -> float:
        """Measure database query round-trip latency in milliseconds."""
        start = time.perf_counter()
        self.db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000.0
        return round(latency, 2)

    def list_pending_outbox(self, limit: int = 100) -> Sequence[OutboxEvent]:
        return self.outbox_repo.list_unpublished(limit=limit)

    def count_pending_outbox(self) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.published.is_(False))
        )
        return self.db.scalar(stmt) or 0

    def get_platform_stats(self) -> dict[str, int]:
        total_tenants = self.db.scalar(select(func.count()).select_from(Tenant)) or 0
        total_agents = self.db.scalar(select(func.count()).select_from(Agent)) or 0
        total_conversations = (
            self.db.scalar(select(func.count()).select_from(Conversation)) or 0
        )
        total_docs = (
            self.db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
        )

        return {
            "total_tenants": total_tenants,
            "total_agents": total_agents,
            "total_conversations": total_conversations,
            "total_knowledge_docs": total_docs,
        }

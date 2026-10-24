"""Agents domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Agent, AgentTool
from app.db.repositories.agent import AgentRepository, ToolRepository


class AgentDomainRepository(AgentRepository):
    """Domain-specific repository extending standard AgentRepository."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.tools = ToolRepository(db)

    def count_by_tenant(self, tenant_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Agent).where(Agent.tenant_id == tenant_id)
        return self.db.scalar(stmt) or 0

    def list_with_tools(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Sequence[Agent]:
        stmt = (
            select(Agent)
            .where(Agent.tenant_id == tenant_id)
            .options(selectinload(Agent.agent_tools).selectinload(AgentTool.tool))
            .order_by(Agent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

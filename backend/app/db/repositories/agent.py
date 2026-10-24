"""Agent and Tool repositories with tenant isolation."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Agent, AgentStatus, AgentTool, ToolDefinition
from app.db.repositories.base import TenantScopedRepository


class AgentRepository(TenantScopedRepository[Agent]):
    """Repository managing tenant AI agents."""

    def __init__(self, db: Session):
        super().__init__(Agent, db)

    def create(
        self,
        tenant_id: uuid.UUID,
        name: str,
        instructions: str,
        model_id: str = "gemini-2.5-flash",
        description: str | None = None,
        model_config_json: dict[str, Any] | None = None,
        status: str = AgentStatus.ACTIVE.value,
    ) -> Agent:
        agent = Agent(
            tenant_id=tenant_id,
            name=name,
            instructions=instructions,
            model_id=model_id,
            description=description,
            model_config_json=model_config_json or {},
            status=status,
        )
        return self.add(agent)

    def get_with_tools(self, agent_id: uuid.UUID, tenant_id: uuid.UUID) -> Agent | None:
        """Fetch agent ensuring tenant boundary and eager loading assigned tools."""
        stmt = (
            select(Agent)
            .where(Agent.id == agent_id, Agent.tenant_id == tenant_id)
            .options(selectinload(Agent.agent_tools).selectinload(AgentTool.tool))
        )
        return self.db.scalars(stmt).first()


class ToolRepository:
    """Repository managing tool definitions and agent permissions."""

    def __init__(self, db: Session):
        self.db = db

    def create_definition(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        tenant_id: uuid.UUID | None = None,
        requires_confirmation: bool = False,
    ) -> ToolDefinition:
        tool = ToolDefinition(
            tenant_id=tenant_id,
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            requires_confirmation=requires_confirmation,
        )
        self.db.add(tool)
        self.db.flush()
        return tool

    def get_definition(
        self, tool_id: uuid.UUID, tenant_id: uuid.UUID | None = None
    ) -> ToolDefinition | None:
        """Get tool definition if global (tenant_id is NULL) or matching the given tenant."""
        stmt = select(ToolDefinition).where(ToolDefinition.id == tool_id)
        if tenant_id is not None:
            stmt = stmt.where(
                (ToolDefinition.tenant_id == tenant_id) | (ToolDefinition.tenant_id.is_(None))
            )
        return self.db.scalars(stmt).first()

    def list_accessible(self, tenant_id: uuid.UUID) -> Sequence[ToolDefinition]:
        """List all tools accessible to a tenant (global tools + tenant's custom tools)."""
        stmt = select(ToolDefinition).where(
            ToolDefinition.is_active.is_(True),
            (ToolDefinition.tenant_id == tenant_id) | (ToolDefinition.tenant_id.is_(None)),
        )
        return self.db.scalars(stmt).all()

    def assign_tool_to_agent(
        self,
        tenant_id: uuid.UUID,
        agent_id: uuid.UUID,
        tool_id: uuid.UUID,
        permission_level: str = "standard",
    ) -> AgentTool:
        """Assign an accessible tool to an agent."""
        assignment = AgentTool(
            tenant_id=tenant_id,
            agent_id=agent_id,
            tool_id=tool_id,
            permission_level=permission_level,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

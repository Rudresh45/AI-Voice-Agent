"""Agents domain service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, EntityNotFoundError
from app.modules.agents.models import Agent
from app.modules.agents.repository import AgentDomainRepository
from app.modules.agents.schemas import AgentCreate, AgentRead, AgentUpdate


class AgentService:
    """Business operations for tenant agents."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = AgentDomainRepository(db)

    def create_agent(self, tenant_id: uuid.UUID, data: AgentCreate) -> AgentRead:
        # Prevent secret leakage in model_config_json
        sanitized_config = {
            k: v for k, v in data.model_config_json.items()
            if not any(secret_term in k.lower() for secret_term in ("key", "secret", "token", "password"))
        }

        # Check unique name within tenant
        existing = self.repo.list_scoped(tenant_id)
        if any(a.name.lower() == data.name.lower() for a in existing):
            raise ConflictError(f"Agent with name '{data.name}' already exists in this tenant.")

        agent = self.repo.create(
            tenant_id=tenant_id,
            name=data.name,
            instructions=data.instructions,
            model_id=data.model_id,
            description=data.description,
            model_config_json=sanitized_config,
        )

        # Assign requested tools
        for tool_id in data.tool_ids:
            tool = self.repo.tools.get_definition(tool_id, tenant_id)
            if tool is not None:
                self.repo.tools.assign_tool_to_agent(tenant_id, agent.id, tool.id)

        self.db.commit()
        full_agent = self.repo.get_with_tools(agent.id, tenant_id)
        return AgentRead.model_validate(full_agent)

    def get_agent(self, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> AgentRead:
        agent = self.repo.get_with_tools(agent_id, tenant_id)
        if agent is None:
            raise EntityNotFoundError("Agent", agent_id)
        return AgentRead.model_validate(agent)

    def list_agents(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[Agent], int]:
        total = self.repo.count_by_tenant(tenant_id)
        agents = self.repo.list_with_tools(tenant_id, skip=skip, limit=limit)
        return agents, total

    def update_agent(
        self, tenant_id: uuid.UUID, agent_id: uuid.UUID, data: AgentUpdate
    ) -> AgentRead:
        agent = self.repo.get_by_id_scoped(agent_id, tenant_id)

        if data.name is not None and data.name != agent.name:
            # Check collision
            existing = self.repo.list_scoped(tenant_id)
            if any(a.name.lower() == data.name.lower() and a.id != agent_id for a in existing):
                raise ConflictError(f"Agent name '{data.name}' already in use.")
            agent.name = data.name

        if data.instructions is not None:
            agent.instructions = data.instructions
        if data.model_id is not None:
            agent.model_id = data.model_id
        if data.description is not None:
            agent.description = data.description
        if data.model_config_json is not None:
            sanitized_config = {
                k: v for k, v in data.model_config_json.items()
                if not any(s in k.lower() for s in ("key", "secret", "token", "password"))
            }
            agent.model_config_json = sanitized_config
        if data.status is not None:
            agent.status = data.status

        self.db.commit()
        full_agent = self.repo.get_with_tools(agent_id, tenant_id)
        return AgentRead.model_validate(full_agent)

    def delete_agent(self, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        self.repo.delete_scoped(agent_id, tenant_id)
        self.db.commit()

    def assign_tool(
        self, tenant_id: uuid.UUID, agent_id: uuid.UUID, tool_id: uuid.UUID
    ) -> AgentRead:
        # Verify agent exists in tenant
        self.repo.get_by_id_scoped(agent_id, tenant_id)
        # Verify tool is accessible to tenant
        tool = self.repo.tools.get_definition(tool_id, tenant_id)
        if tool is None:
            raise EntityNotFoundError("ToolDefinition", tool_id)

        self.repo.tools.assign_tool_to_agent(tenant_id, agent_id, tool_id)
        self.db.commit()
        full_agent = self.repo.get_with_tools(agent_id, tenant_id)
        return AgentRead.model_validate(full_agent)

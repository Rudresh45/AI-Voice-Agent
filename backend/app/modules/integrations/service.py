"""Integrations domain service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, EntityNotFoundError
from app.modules.integrations.models import ToolDefinition
from app.modules.integrations.repository import IntegrationsRepository
from app.modules.integrations.schemas import ToolDefinitionCreate, ToolDefinitionRead


class IntegrationsService:
    """Business operations for custom and platform tools."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = IntegrationsRepository(db)

    def create_custom_tool(
        self, tenant_id: uuid.UUID, data: ToolDefinitionCreate
    ) -> ToolDefinitionRead:
        accessible = self.repo.list_accessible(tenant_id)
        if any(t.name.lower() == data.name.lower() for t in accessible):
            raise ConflictError(f"Tool with name '{data.name}' is already accessible in this tenant.")

        tool = self.repo.create_definition(
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            parameters_schema=data.parameters_schema,
            requires_confirmation=data.requires_confirmation,
        )
        self.db.commit()
        return ToolDefinitionRead.model_validate(tool)

    def list_accessible_tools(self, tenant_id: uuid.UUID) -> Sequence[ToolDefinition]:
        return self.repo.list_accessible(tenant_id)

    def get_tool(self, tenant_id: uuid.UUID, tool_id: uuid.UUID) -> ToolDefinitionRead:
        tool = self.repo.get_definition(tool_id, tenant_id)
        if tool is None:
            raise EntityNotFoundError("ToolDefinition", tool_id)
        return ToolDefinitionRead.model_validate(tool)

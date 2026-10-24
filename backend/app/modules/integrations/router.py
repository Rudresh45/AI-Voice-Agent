"""Integrations domain API router."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_tenant, get_db
from app.db.models import Tenant
from app.modules.integrations.schemas import ToolDefinitionCreate, ToolDefinitionRead
from app.modules.integrations.service import IntegrationsService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.post("/tools", response_model=ToolDefinitionRead, status_code=status.HTTP_201_CREATED, summary="Create custom tool")
def create_tool(
    data: ToolDefinitionCreate,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> ToolDefinitionRead:
    service = IntegrationsService(db)
    return service.create_custom_tool(current_tenant.id, data)


@router.get("/tools", response_model=list[ToolDefinitionRead], summary="List accessible tools")
def list_tools(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> Sequence[ToolDefinitionRead]:
    service = IntegrationsService(db)
    tools = service.list_accessible_tools(current_tenant.id)
    return [ToolDefinitionRead.model_validate(t) for t in tools]


@router.get("/tools/{tool_id}", response_model=ToolDefinitionRead, summary="Get tool definition")
def get_tool(
    tool_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> ToolDefinitionRead:
    service = IntegrationsService(db)
    return service.get_tool(current_tenant.id, tool_id)

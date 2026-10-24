"""Agents domain API router with RBAC enforcement."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    RequestContext,
    get_current_tenant,
    get_db,
    require_admin_access,
    require_write_access,
)
from app.core.pagination import PageParams, PaginatedResponse
from app.db.models import Tenant
from app.modules.agents.schemas import AgentCreate, AgentRead, AgentUpdate
from app.modules.agents.service import AgentService

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post("/", response_model=AgentRead, status_code=status.HTTP_201_CREATED, summary="Create an agent")
def create_agent(
    data: AgentCreate,
    context: Annotated[RequestContext, Depends(require_write_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AgentRead:
    service = AgentService(db)
    return service.create_agent(context.tenant.id, data)


@router.get("/", response_model=PaginatedResponse[AgentRead], summary="List tenant agents")
def list_agents(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
    page_params: Annotated[PageParams, Depends()],
) -> PaginatedResponse[AgentRead]:
    service = AgentService(db)
    agents, total = service.list_agents(
        current_tenant.id, skip=page_params.offset, limit=page_params.per_page
    )
    items = [AgentRead.model_validate(a) for a in agents]
    return page_params.make_response(items, total)


@router.get("/{agent_id}", response_model=AgentRead, summary="Get agent by ID")
def get_agent(
    agent_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> AgentRead:
    service = AgentService(db)
    return service.get_agent(current_tenant.id, agent_id)


@router.patch("/{agent_id}", response_model=AgentRead, summary="Update agent")
def update_agent(
    agent_id: uuid.UUID,
    data: AgentUpdate,
    context: Annotated[RequestContext, Depends(require_write_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AgentRead:
    service = AgentService(db)
    return service.update_agent(context.tenant.id, agent_id, data)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete agent")
def delete_agent(
    agent_id: uuid.UUID,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    service = AgentService(db)
    service.delete_agent(context.tenant.id, agent_id)


@router.post("/{agent_id}/tools/{tool_id}", response_model=AgentRead, summary="Assign tool to agent")
def assign_tool_to_agent(
    agent_id: uuid.UUID,
    tool_id: uuid.UUID,
    context: Annotated[RequestContext, Depends(require_write_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AgentRead:
    service = AgentService(db)
    return service.assign_tool(context.tenant.id, agent_id, tool_id)

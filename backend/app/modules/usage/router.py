"""Usage domain API router with RBAC enforcement."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    RequestContext,
    get_current_tenant,
    get_db,
    require_write_access,
)
from app.db.models import Tenant
from app.modules.usage.schemas import (
    UsageEventRead,
    UsageRecordCreate,
    UsageSummaryResponse,
)
from app.modules.usage.service import UsageService

router = APIRouter(prefix="/usage", tags=["Usage"])


@router.post("/", response_model=UsageEventRead, status_code=status.HTTP_201_CREATED, summary="Record a usage event")
def record_usage_event(
    data: UsageRecordCreate,
    context: Annotated[RequestContext, Depends(require_write_access)],
    db: Annotated[Session, Depends(get_db)],
) -> UsageEventRead:
    service = UsageService(db)
    return service.record_event(context.tenant.id, data)


@router.get("/", response_model=UsageSummaryResponse, summary="Get usage summary for tenant")
def get_usage_summary(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> UsageSummaryResponse:
    service = UsageService(db)
    return service.get_summary(current_tenant.id)

"""Usage domain API router."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_tenant, get_db
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
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> UsageEventRead:
    service = UsageService(db)
    return service.record_event(current_tenant.id, data)


@router.get("/", response_model=UsageSummaryResponse, summary="Get usage summary for tenant")
def get_usage_summary(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> UsageSummaryResponse:
    service = UsageService(db)
    return service.get_summary(current_tenant.id)

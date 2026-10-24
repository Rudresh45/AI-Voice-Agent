"""Audit domain API router."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_tenant, get_db
from app.core.pagination import PageParams, PaginatedResponse
from app.db.models import Tenant
from app.modules.audit.schemas import AuditEventRead
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/", response_model=PaginatedResponse[AuditEventRead], summary="List tenant audit logs")
def list_audit_events(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
    page_params: Annotated[PageParams, Depends()],
) -> PaginatedResponse[AuditEventRead]:
    service = AuditService(db)
    events, total = service.list_events(
        current_tenant.id, skip=page_params.offset, limit=page_params.per_page
    )
    items = [AuditEventRead.model_validate(e) for e in events]
    return page_params.make_response(items, total)

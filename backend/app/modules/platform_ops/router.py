"""Platform ops domain API router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.modules.platform_ops.schemas import (
    OutboxEventRead,
    PlatformStatsResponse,
    SystemHealthResponse,
)
from app.modules.platform_ops.service import PlatformOpsService

router = APIRouter(prefix="/platform-ops", tags=["Platform Ops"])


@router.get("/health", response_model=SystemHealthResponse, summary="Platform system health check")
def platform_health(
    db: Annotated[Session, Depends(get_db)],
) -> SystemHealthResponse:
    service = PlatformOpsService(db)
    return service.check_health()


@router.get("/stats", response_model=PlatformStatsResponse, summary="Platform entity aggregate counts")
def platform_stats(
    db: Annotated[Session, Depends(get_db)],
) -> PlatformStatsResponse:
    service = PlatformOpsService(db)
    return service.get_stats()


@router.get("/outbox/pending", response_model=list[OutboxEventRead], summary="List pending transactional outbox events")
def pending_outbox_events(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[OutboxEventRead]:
    service = PlatformOpsService(db)
    return service.get_pending_outbox(limit=limit)

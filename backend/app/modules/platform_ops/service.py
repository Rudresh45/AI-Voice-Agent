"""Platform ops domain service."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.modules.platform_ops.repository import PlatformOpsRepository
from app.modules.platform_ops.schemas import (
    OutboxEventRead,
    PlatformStatsResponse,
    SystemHealthResponse,
)

logger = logging.getLogger(__name__)


class PlatformOpsService:
    """Service handling platform operations, stats, and operational health."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = PlatformOpsRepository(db)

    def check_health(self) -> SystemHealthResponse:
        try:
            latency = self.repo.ping_db()
            db_status = "connected"
            status = "healthy"
        except Exception as exc:  # noqa: BLE001
            logger.error("Platform health check failed database ping: %s", exc)
            db_status = "disconnected"
            status = "degraded"
            latency = -1.0

        pending_count = self.repo.count_pending_outbox() if db_status == "connected" else -1

        return SystemHealthResponse(
            status=status,
            database=db_status,
            pending_outbox_events=pending_count,
            latency_ms=latency,
        )

    def get_stats(self) -> PlatformStatsResponse:
        stats = self.repo.get_platform_stats()
        return PlatformStatsResponse(**stats)

    def get_pending_outbox(self, limit: int = 50) -> list[OutboxEventRead]:
        events = self.repo.list_pending_outbox(limit=limit)
        return [OutboxEventRead.model_validate(e) for e in events]

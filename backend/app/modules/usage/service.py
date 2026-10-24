"""Usage domain service."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.modules.usage.repository import UsageRepository
from app.modules.usage.schemas import (
    UsageEventRead,
    UsageRecordCreate,
    UsageSummaryItem,
    UsageSummaryResponse,
)


class UsageService:
    """Business operations for usage metering and reporting."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = UsageRepository(db)

    def record_event(self, tenant_id: uuid.UUID, data: UsageRecordCreate) -> UsageEventRead:
        event = self.repo.record_usage(
            tenant_id=tenant_id,
            event_type=data.event_type,
            quantity=data.quantity,
            unit=data.unit,
            meta_data=data.meta_data,
        )
        self.db.commit()
        return UsageEventRead.model_validate(event)

    def get_summary(self, tenant_id: uuid.UUID) -> UsageSummaryResponse:
        aggregations = self.repo.aggregate_by_tenant(tenant_id)
        items = [
            UsageSummaryItem(
                event_type=row[0],
                total_quantity=int(row[1]),
                unit=row[2],
            )
            for row in aggregations
        ]
        return UsageSummaryResponse(tenant_id=tenant_id, summary=items)

"""Usage domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import UsageEvent
from app.db.repositories.base import TenantScopedRepository


class UsageRepository(TenantScopedRepository[UsageEvent]):
    """Repository handling usage events and aggregation summaries."""

    def __init__(self, db: Session):
        super().__init__(UsageEvent, db)

    def record_usage(
        self,
        tenant_id: uuid.UUID,
        event_type: str,
        quantity: int,
        unit: str,
        meta_data: dict[str, str] | None = None,
    ) -> UsageEvent:
        event = UsageEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            quantity=quantity,
            unit=unit,
            meta_data=meta_data or {},
        )
        return self.add(event)

    def aggregate_by_tenant(self, tenant_id: uuid.UUID) -> Sequence[tuple[str, int, str]]:
        stmt = (
            select(
                UsageEvent.event_type,
                func.sum(UsageEvent.quantity).label("total_quantity"),
                UsageEvent.unit,
            )
            .where(UsageEvent.tenant_id == tenant_id)
            .group_by(UsageEvent.event_type, UsageEvent.unit)
        )
        return self.db.execute(stmt).all()  # type: ignore[return-value]

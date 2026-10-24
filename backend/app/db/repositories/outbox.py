"""Transactional Outbox repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OutboxEvent
from app.db.repositories.base import BaseRepository


class OutboxRepository(BaseRepository[OutboxEvent]):
    """Repository managing reliable transactional outbox events."""

    def __init__(self, db: Session):
        super().__init__(OutboxEvent, db)

    def record_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            published=False,
        )
        return self.add(event)

    def list_unpublished(self, limit: int = 100) -> Sequence[OutboxEvent]:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published.is_(False))
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def mark_published(self, event_id: uuid.UUID) -> None:
        event = self.get_by_id(event_id)
        if event is not None:
            event.published = True
            event.published_at = datetime.now(UTC)
            self.db.flush()

    def record_failure(self, event_id: uuid.UUID, error_message: str) -> None:
        event = self.get_by_id(event_id)
        if event is not None:
            event.retry_count += 1
            event.last_error = error_message
            self.db.flush()

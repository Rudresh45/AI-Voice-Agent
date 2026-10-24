"""Audit and Outbox repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, AuditOutcome, OutboxEvent
from app.db.repositories.base import BaseRepository, TenantScopedRepository


class AuditRepository(TenantScopedRepository[AuditEvent]):
    """Repository recording immutable security and compliance events."""

    def __init__(self, db: Session):
        super().__init__(AuditEvent, db)

    def record(
        self,
        tenant_id: uuid.UUID,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        outcome: str = AuditOutcome.SUCCESS.value,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            details=details or {},
            ip_address=ip_address,
        )
        return self.add(event)

    def list_by_action(
        self,
        tenant_id: uuid.UUID,
        action: str,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action)
            .order_by(AuditEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()


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

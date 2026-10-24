"""Audit domain service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.audit.repository import AuditDomainRepository
from app.modules.audit.schemas import AuditEventRead


class AuditService:
    """Business operations for security and audit trail."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = AuditDomainRepository(db)

    def log_action(
        self,
        tenant_id: uuid.UUID,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        outcome: str = "success",
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditEventRead:
        event = self.repo.record(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            details=details,
            ip_address=ip_address,
        )
        self.db.commit()
        return AuditEventRead.model_validate(event)

    def list_events(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[AuditEvent], int]:
        total = self.repo.count_by_tenant(tenant_id)
        events = self.repo.list_paginated(tenant_id, skip=skip, limit=limit)
        return events, total

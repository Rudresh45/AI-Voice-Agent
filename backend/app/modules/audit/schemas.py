"""Audit domain schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    outcome: str
    details: dict[str, Any]
    ip_address: str | None
    created_at: datetime

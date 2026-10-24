"""Platform ops domain schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OutboxEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any]
    published: bool
    retry_count: int
    last_error: str | None
    created_at: datetime
    published_at: datetime | None


class SystemHealthResponse(BaseModel):
    status: str
    database: str
    pending_outbox_events: int
    latency_ms: float


class PlatformStatsResponse(BaseModel):
    total_tenants: int
    total_agents: int
    total_conversations: int
    total_knowledge_docs: int

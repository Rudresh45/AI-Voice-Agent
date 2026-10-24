"""Usage domain schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UsageRecordCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0)
    unit: str = Field(min_length=1, max_length=32)
    meta_data: dict[str, Any] = Field(default_factory=dict)


class UsageEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    event_type: str
    quantity: int
    unit: str
    created_at: datetime


class UsageSummaryItem(BaseModel):
    event_type: str
    total_quantity: int
    unit: str


class UsageSummaryResponse(BaseModel):
    tenant_id: uuid.UUID
    summary: list[UsageSummaryItem]

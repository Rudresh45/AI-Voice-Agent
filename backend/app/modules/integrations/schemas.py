"""Integrations domain schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False


class ToolDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    name: str
    description: str
    parameters_schema: dict[str, Any]
    requires_confirmation: bool
    is_active: bool
    created_at: datetime

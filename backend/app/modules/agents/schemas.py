"""Agents domain schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    requires_confirmation: bool


class AgentToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool_id: uuid.UUID
    is_enabled: bool
    permission_level: str
    tool: ToolSummary


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=10000)
    model_id: str = Field(default="gemini-2.5-flash", min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    model_config_json: dict[str, Any] = Field(default_factory=dict)
    tool_ids: list[uuid.UUID] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    instructions: str | None = Field(default=None, min_length=1, max_length=10000)
    model_id: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    model_config_json: dict[str, Any] | None = None
    status: str | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    instructions: str
    model_id: str
    model_config_json: dict[str, Any]
    status: str
    created_at: datetime
    agent_tools: list[AgentToolRead] = Field(default_factory=list)

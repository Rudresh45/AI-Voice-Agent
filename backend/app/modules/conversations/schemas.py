"""Conversations domain schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    token_count: int | None = None
    meta_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant|system|tool)$")
    content: str = Field(min_length=1)
    token_count: int | None = None
    meta_data: dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    agent_id: uuid.UUID
    title: str | None = Field(default=None, max_length=255)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    user_id: uuid.UUID | None
    title: str | None
    status: str
    created_at: datetime
    messages: list[MessageRead] = Field(default_factory=list)

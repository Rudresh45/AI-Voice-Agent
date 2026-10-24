"""Knowledge domain schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=512)
    content_type: str = Field(min_length=1, max_length=120)
    byte_size: int = Field(gt=0)
    checksum_sha256: str = Field(min_length=64, max_length=64)
    meta_data: dict[str, Any] = Field(default_factory=dict)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    storage_key: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    ingestion_status: str
    created_at: datetime

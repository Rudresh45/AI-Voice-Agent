"""Identity domain schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    email: str
    display_name: str | None
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str | None = Field(default=None, max_length=120)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)


class MembershipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    status: str


class UserProfileResponse(BaseModel):
    user: UserRead
    memberships: list[MembershipSummary]

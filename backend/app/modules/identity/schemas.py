"""Identity domain schemas."""

from __future__ import annotations

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
    is_platform_admin: bool = False
    created_at: datetime


class UserCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)


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


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    session_token: str
    expires_at: datetime
    user: UserRead


class UserSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_revoked: bool
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime


class PasswordSetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class LogoutResponse(BaseModel):
    message: str = "Successfully logged out."

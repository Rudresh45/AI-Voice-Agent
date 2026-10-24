"""Typed input and output schemas for agent tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseToolInput(BaseModel):
    """Base schema for tool arguments with strict validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BaseToolOutput(BaseModel):
    """Base schema for structured tool execution results."""

    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------------------
# Business Tool Schemas
# ---------------------------------------------------------------------------


class LookupCustomerInput(BaseToolInput):
    """Arguments for looking up customer details."""

    customer_id: str = Field(
        ..., min_length=1, max_length=64, description="Unique customer ID (e.g. CUST-1001)"
    )
    include_notes: bool = Field(
        default=False, description="Whether to include internal customer notes"
    )


class LookupCustomerOutput(BaseToolOutput):
    """Structured response from customer lookup."""

    customer_id: str
    name: str
    status: str
    tier: str
    email: str
    notes: str | None = None


class KnowledgeSearchResult(BaseModel):
    document_id: str
    title: str
    content_snippet: str
    score: float = 1.0


class SearchKnowledgeBaseInput(BaseToolInput):
    """Arguments for searching the tenant's knowledge repository."""

    query: str = Field(
        ..., min_length=2, max_length=256, description="Search query or customer question"
    )
    top_k: int = Field(
        default=3, ge=1, le=10, description="Maximum number of relevant articles to retrieve"
    )


class SearchKnowledgeBaseOutput(BaseToolOutput):
    """Structured response containing verified knowledge documents."""

    query: str
    results: list[KnowledgeSearchResult] = Field(default_factory=list)


class ScheduleCallbackInput(BaseToolInput):
    """Arguments for scheduling a customer support callback."""

    customer_id: str = Field(
        ..., min_length=1, max_length=64, description="Customer identifier"
    )
    callback_time: str = Field(
        ..., min_length=5, max_length=64, description="Requested callback time or ISO timestamp"
    )
    phone_number: str = Field(
        ..., min_length=7, max_length=20, description="Contact phone number"
    )
    reason: str = Field(
        default="General inquiry", max_length=200, description="Callback topic"
    )
    idempotency_key: str = Field(
        ..., min_length=1, max_length=128, description="Client idempotency key for safe retries"
    )


class ScheduleCallbackOutput(BaseToolOutput):
    """Structured result of scheduled callback."""

    confirmation_id: str
    customer_id: str
    scheduled_time: str
    status: str
    idempotency_key: str


class CancelReservationInput(BaseToolInput):
    """Arguments for cancelling a customer booking or reservation (consequential action)."""

    reservation_id: str = Field(
        ..., min_length=1, max_length=64, description="Reservation identifier to cancel"
    )
    reason: str = Field(
        ..., min_length=3, max_length=300, description="Mandatory reason for cancellation"
    )
    idempotency_key: str = Field(
        ..., min_length=1, max_length=128, description="Client idempotency key for safe retries"
    )


class CancelReservationOutput(BaseToolOutput):
    """Structured result of cancellation."""

    reservation_id: str
    status: str
    refund_eligible: bool
    message: str
    idempotency_key: str


class ToolExecutionRecord(BaseModel):
    """Audit snapshot of a single tool execution attempt."""

    tool_name: str
    call_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    status: str  # approved, completed, rejected, failed, confirmation_required
    error_message: str | None = None
    duration_ms: int = 0

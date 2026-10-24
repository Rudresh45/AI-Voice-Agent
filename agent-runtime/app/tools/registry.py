"""Typed tool registry with Pydantic validation and Gemini schema export."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from google.genai import types
from pydantic import BaseModel, ValidationError

from app.policies.authorization import PrincipalContext
from app.tools.schemas import (
    CancelReservationInput,
    CancelReservationOutput,
    KnowledgeSearchResult,
    LookupCustomerInput,
    LookupCustomerOutput,
    ScheduleCallbackInput,
    ScheduleCallbackOutput,
    SearchKnowledgeBaseInput,
    SearchKnowledgeBaseOutput,
)

logger = logging.getLogger("agent_runtime.tools")


class ToolError(Exception):
    """Base error for tool registry and execution operations."""


class UnregisteredToolError(ToolError):
    """Raised when an agent attempts to invoke a tool that is not allowlisted."""


class MalformedArgumentsError(ToolError):
    """Raised when tool arguments fail Pydantic schema validation."""


class ToolExecutionError(ToolError):
    """Raised when an authorized tool fails during execution."""


@dataclass(frozen=True)
class Tool:
    """Definition of an authorized agent tool with typed schemas and security policies."""

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    handler: Callable[[PrincipalContext, Any], Any]
    requires_confirmation: bool = False
    is_side_effecting: bool = False

    def validate_input(self, raw_args: dict[str, Any]) -> BaseModel:
        """Validate and parse raw model arguments against the input schema."""
        try:
            return self.input_schema.model_validate(raw_args)
        except ValidationError as exc:
            raise MalformedArgumentsError(
                f"Arguments for tool '{self.name}' failed schema validation: {exc}"
            ) from exc

    def to_gemini_declaration(self) -> types.FunctionDeclaration:
        """Export tool metadata to Gemini OpenAPI-compatible FunctionDeclaration."""
        schema = self.input_schema.model_json_schema()
        # Clean title to avoid clutter
        schema.pop("title", None)
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=schema,
        )


class ToolRegistry:
    """Registry maintaining authorized tools and schema declarations."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a new tool specification."""
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (side_effecting=%s)", tool.name, tool.is_side_effecting)

    def get(self, name: str) -> Tool:
        """Retrieve a registered tool by name; fails closed if unregistered."""
        if name not in self._tools:
            logger.warning("Unregistered tool requested: %s", name)
            raise UnregisteredToolError(
                f"Tool '{name}' is not registered or allowlisted in this platform."
            )
        return self._tools[name]

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_gemini_tools(self, allowed_names: set[str] | None = None) -> list[types.Tool]:
        """Produce the list of Gemini Tool definitions filtered by allowed permissions."""
        declarations: list[types.FunctionDeclaration] = []
        for name, tool in self._tools.items():
            if allowed_names is None or name in allowed_names:
                declarations.append(tool.to_gemini_declaration())

        if not declarations:
            return []
        return [types.Tool(function_declarations=declarations)]


# ---------------------------------------------------------------------------
# Authorized Business Backend Handlers (Default Implementation)
# ---------------------------------------------------------------------------


def handle_lookup_customer(
    context: PrincipalContext, data: LookupCustomerInput
) -> LookupCustomerOutput:
    """Authorized backend query: look up customer info scoped to tenant."""
    # Never execute arbitrary SQL; execute strict domain business operation
    logger.info("Executing customer lookup for tenant=%s, cust=%s", context.tenant_id, data.customer_id)
    return LookupCustomerOutput(
        customer_id=data.customer_id,
        name="Alex Smith",
        status="ACTIVE",
        tier="Enterprise VIP",
        email="alex.smith@example.com",
        notes="High-priority enterprise account" if data.include_notes else None,
    )


def handle_search_knowledge_base(
    context: PrincipalContext, data: SearchKnowledgeBaseInput
) -> SearchKnowledgeBaseOutput:
    """Authorized backend query: search tenant-scoped knowledge base."""
    logger.info("Executing KB search for tenant=%s, query=%s", context.tenant_id, data.query)
    results = [
        KnowledgeSearchResult(
            document_id="doc-kb-001",
            title="Billing and Refund Policy",
            content_snippet="Refunds are fully eligible within 30 days of booking if cancelled prior to check-in.",
            score=0.95,
        ),
        KnowledgeSearchResult(
            document_id="doc-kb-002",
            title="Support Hours and Escalations",
            content_snippet="Enterprise support callbacks are processed between 08:00 and 20:00 UTC.",
            score=0.88,
        ),
    ]
    return SearchKnowledgeBaseOutput(query=data.query, results=results[: data.top_k])


def handle_schedule_callback(
    context: PrincipalContext, data: ScheduleCallbackInput
) -> ScheduleCallbackOutput:
    """Authorized backend mutation: schedule support callback with idempotency."""
    logger.info(
        "Scheduling callback for tenant=%s, cust=%s, time=%s, key=%s",
        context.tenant_id,
        data.customer_id,
        data.callback_time,
        data.idempotency_key,
    )
    return ScheduleCallbackOutput(
        confirmation_id=f"cb-{data.idempotency_key[:8]}",
        customer_id=data.customer_id,
        scheduled_time=data.callback_time,
        status="CONFIRMED",
        idempotency_key=data.idempotency_key,
    )


def handle_cancel_reservation(
    context: PrincipalContext, data: CancelReservationInput
) -> CancelReservationOutput:
    """Authorized consequential mutation: cancel reservation with idempotency."""
    logger.info(
        "Cancelling reservation for tenant=%s, res_id=%s, reason=%s",
        context.tenant_id,
        data.reservation_id,
        data.reason,
    )
    return CancelReservationOutput(
        reservation_id=data.reservation_id,
        status="CANCELLED",
        refund_eligible=True,
        message=f"Reservation {data.reservation_id} has been cancelled successfully.",
        idempotency_key=data.idempotency_key,
    )


def get_default_tool_registry() -> ToolRegistry:
    """Construct the standard authorized tool registry."""
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="lookup_customer",
            description="Look up verified customer account details, status, and tier by customer ID.",
            input_schema=LookupCustomerInput,
            output_schema=LookupCustomerOutput,
            handler=handle_lookup_customer,
            requires_confirmation=False,
            is_side_effecting=False,
        )
    )

    registry.register(
        Tool(
            name="search_knowledge_base",
            description="Search the tenant's verified company policies, documentation, and FAQs.",
            input_schema=SearchKnowledgeBaseInput,
            output_schema=SearchKnowledgeBaseOutput,
            handler=handle_search_knowledge_base,
            requires_confirmation=False,
            is_side_effecting=False,
        )
    )

    registry.register(
        Tool(
            name="schedule_callback",
            description="Schedule an authorized customer service callback with an idempotency key.",
            input_schema=ScheduleCallbackInput,
            output_schema=ScheduleCallbackOutput,
            handler=handle_schedule_callback,
            requires_confirmation=False,
            is_side_effecting=True,
        )
    )

    registry.register(
        Tool(
            name="cancel_reservation",
            description="Cancel an active customer booking or reservation. This is a consequential action requiring user confirmation.",
            input_schema=CancelReservationInput,
            output_schema=CancelReservationOutput,
            handler=handle_cancel_reservation,
            requires_confirmation=True,
            is_side_effecting=True,
        )
    )

    return registry

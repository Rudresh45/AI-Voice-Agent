"""Policy engine and authorization interface for agent tool execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("agent_runtime.policies")


class AuthorizationStatus(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"


@dataclass(frozen=True)
class PrincipalContext:
    """Server-resolved, immutable principal identity and tenant boundary."""

    tenant_id: str
    user_id: str | None = None
    role: str = "agent_operator"
    allowed_tools: set[str] = field(default_factory=set)
    confirmed_actions: set[str] = field(default_factory=set)

    def __post_init__(self):
        if not self.tenant_id or not isinstance(self.tenant_id, str):
            raise ValueError("PrincipalContext must contain a valid non-empty tenant_id")


@dataclass
class AuthorizationResult:
    """Outcome of policy evaluation for a specific tool call."""

    status: AuthorizationStatus
    reason: str
    confirmation_payload: dict[str, Any] | None = None

    @property
    def is_approved(self) -> bool:
        return self.status == AuthorizationStatus.APPROVED


class PolicyEngine:
    """Enforces zero-trust authorization, tenant isolation, and confirmation policies."""

    # Disallowed roles for mutation / side-effecting operations
    READ_ONLY_ROLES = frozenset({"read_only", "viewer", "anonymous"})

    def authorize_tool(
        self,
        *,
        tool_name: str,
        is_side_effecting: bool,
        requires_confirmation: bool,
        context: PrincipalContext | None,
        arguments: dict[str, Any],
    ) -> AuthorizationResult:
        """Evaluate access authorization for a tool invocation against trusted context.

        Fails closed on any ambiguity, missing context, or policy violation.
        """
        # Rule 1: Fail closed if context or tenant is absent
        if context is None:
            logger.warning("Tool %s denied: Missing PrincipalContext (fail closed)", tool_name)
            return AuthorizationResult(
                status=AuthorizationStatus.DENIED,
                reason="Authentication and principal context required to execute tools.",
            )

        if not context.tenant_id or not context.tenant_id.strip():
            logger.warning("Tool %s denied: Missing tenant_id in context (fail closed)", tool_name)
            return AuthorizationResult(
                status=AuthorizationStatus.DENIED,
                reason="Valid tenant isolation boundary required.",
            )

        # Rule 2: Model-generated tenant_id or permissions spoofing check
        # If the LLM passed its own tenant_id in arguments, ensure it does NOT hijack another tenant
        model_tenant_id = arguments.get("tenant_id")
        if model_tenant_id is not None and str(model_tenant_id).strip() != context.tenant_id:
            logger.warning(
                "Tool %s denied: Model attempted tenant spoofing (%s vs %s)",
                tool_name,
                model_tenant_id,
                context.tenant_id,
            )
            return AuthorizationResult(
                status=AuthorizationStatus.DENIED,
                reason="Cross-tenant access or tenant parameter manipulation detected.",
            )

        # Rule 3: Tool assignment to agent/principal
        if tool_name not in context.allowed_tools:
            logger.warning(
                "Tool %s denied: Not in authorized tools for principal (tenant=%s)",
                tool_name,
                context.tenant_id,
            )
            return AuthorizationResult(
                status=AuthorizationStatus.DENIED,
                reason=f"Tool '{tool_name}' is not authorized or enabled for this agent session.",
            )

        # Rule 4: Role-based permissions for side-effecting tools
        if is_side_effecting and context.role in self.READ_ONLY_ROLES:
            logger.warning(
                "Tool %s denied: Principal role '%s' cannot perform side-effecting operations",
                tool_name,
                context.role,
            )
            return AuthorizationResult(
                status=AuthorizationStatus.DENIED,
                reason=f"Role '{context.role}' does not possess write/mutation permissions.",
            )

        # Rule 5: Consequential actions require explicit human confirmation
        if requires_confirmation:
            action_id = (
                str(arguments.get("idempotency_key") or arguments.get("reservation_id") or tool_name)
            )
            if action_id not in context.confirmed_actions:
                logger.info(
                    "Tool %s requires confirmation: action_id=%s not confirmed",
                    tool_name,
                    action_id,
                )
                return AuthorizationResult(
                    status=AuthorizationStatus.REQUIRES_CONFIRMATION,
                    reason=(
                        f"Action '{tool_name}' is consequential and requires explicit confirmation."
                    ),
                    confirmation_payload={
                        "action_id": action_id,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "prompt": (
                            f"Are you sure you want to execute '{tool_name}' with parameters {arguments}?"
                        ),
                    },
                )

        logger.info(
            "Tool %s authorized for tenant=%s, user=%s, role=%s",
            tool_name,
            context.tenant_id,
            context.user_id,
            context.role,
        )
        return AuthorizationResult(
            status=AuthorizationStatus.APPROVED,
            reason="Tool invocation authorized by policy engine.",
        )

    def sanitize_arguments(
        self,
        arguments: dict[str, Any],
        context: PrincipalContext,
    ) -> dict[str, Any]:
        """Strip or override any model-provided tenant claims with trusted server context."""
        sanitized = dict(arguments)
        # Always inject server-side trusted tenant_id
        sanitized["tenant_id"] = context.tenant_id
        return sanitized

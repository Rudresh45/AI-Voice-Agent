"""Unit tests for Gemini agent harness, typed tool registry, and bounded orchestration."""

from __future__ import annotations

import pytest

from app.harness.runner import AgentConfig, AgentRunner
from app.memory.conversation import ConversationMemory
from app.models.base import (
    ModelAdapter,
    ModelProviderError,
    ModelResponse,
    ModelTimeoutError,
    ToolCall,
    UsageTokens,
)
from app.models.gemini import redact_sensitive
from app.policies.authorization import (
    AuthorizationStatus,
    PolicyEngine,
    PrincipalContext,
)
from app.tools.registry import (
    Tool,
    ToolRegistry,
)
from app.tools.schemas import (
    CancelReservationInput,
    CancelReservationOutput,
)


class MockScriptedModelAdapter(ModelAdapter):
    """Predictable mock adapter returning scripted responses or raising errors."""

    def __init__(self, responses: list[ModelResponse | Exception]):
        self.responses = list(responses)
        self.call_count = 0
        self.recorded_calls: list[dict] = []

    def generate(
        self,
        contents,
        *,
        system_instruction=None,
        tools=None,
        config=None,
    ) -> ModelResponse:
        self.recorded_calls.append({
            "contents": contents,
            "system_instruction": system_instruction,
            "tools": tools,
        })
        if self.call_count >= len(self.responses):
            return ModelResponse(content="Fallback: No more scripted responses.")
        resp = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(resp, Exception):
            raise resp
        return resp


@pytest.fixture
def default_context() -> PrincipalContext:
    return PrincipalContext(
        tenant_id="tenant-alpha",
        user_id="user-123",
        role="agent_operator",
        allowed_tools={"lookup_customer", "search_knowledge_base", "schedule_callback", "cancel_reservation"},
    )


# ---------------------------------------------------------------------------
# 1. Acceptance Criterion: Simple text request receives model response
# ---------------------------------------------------------------------------


def test_simple_text_request_receives_model_response(default_context):
    mock_model = MockScriptedModelAdapter([
        ModelResponse(
            content="Hello! How can I assist you with your booking today?",
            usage=UsageTokens(prompt_tokens=15, response_tokens=12, total_tokens=27),
        )
    ])
    runner = AgentRunner(model=mock_model)
    result = runner.execute("Hello", default_context)

    assert result.is_success
    assert result.status == "completed"
    assert "assist you" in result.output_text
    assert result.steps_taken == 1
    assert result.usage["total_tokens"] == 27
    assert len(result.tool_executions) == 0


# ---------------------------------------------------------------------------
# 2. Acceptance Criterion: Valid approved tool call executes through backend
# ---------------------------------------------------------------------------


def test_valid_approved_tool_call_executes(default_context):
    mock_model = MockScriptedModelAdapter([
        # Step 1: Model requests customer lookup
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="lookup_customer",
                    arguments={"customer_id": "CUST-1001", "include_notes": True},
                )
            ],
            usage=UsageTokens(prompt_tokens=20, response_tokens=10, total_tokens=30),
        ),
        # Step 2: Model receives tool result and gives final answer
        ModelResponse(
            content="Customer Alex Smith is an Enterprise VIP account in ACTIVE standing.",
            usage=UsageTokens(prompt_tokens=45, response_tokens=15, total_tokens=60),
        ),
    ])

    runner = AgentRunner(model=mock_model)
    result = runner.execute("Check customer CUST-1001", default_context)

    assert result.is_success
    assert result.steps_taken == 2
    assert "Alex Smith" in result.output_text
    assert len(result.tool_executions) == 1
    te = result.tool_executions[0]
    assert te["tool_name"] == "lookup_customer"
    assert te["status"] == "completed"
    assert te["result"]["customer_id"] == "CUST-1001"
    assert te["result"]["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# 3. Acceptance Criterion: Unregistered tool call is rejected
# ---------------------------------------------------------------------------


def test_unregistered_tool_call_rejected(default_context):
    mock_model = MockScriptedModelAdapter([
        # Step 1: Model requests arbitrary malicious tool
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_x",
                    name="execute_raw_shell_command",
                    arguments={"command": "rm -rf /"},
                )
            ],
        ),
        # Step 2: Model handles the rejection notice
        ModelResponse(
            content="I am sorry, but I do not have access to execute shell commands.",
        ),
    ])

    runner = AgentRunner(model=mock_model)
    result = runner.execute("Run shell command", default_context)

    assert result.is_success
    assert len(result.tool_executions) == 1
    assert result.tool_executions[0]["status"] == "rejected"
    assert "unregistered" in result.tool_executions[0]["error_message"].lower()


# ---------------------------------------------------------------------------
# 4. Acceptance Criterion: Malformed arguments are rejected
# ---------------------------------------------------------------------------


def test_malformed_arguments_rejected(default_context):
    mock_model = MockScriptedModelAdapter([
        # Step 1: Model provides empty customer_id (violates min_length=1)
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_bad",
                    name="lookup_customer",
                    arguments={"customer_id": ""},
                )
            ],
        ),
        # Step 2: Model receives error and asks user for a valid ID
        ModelResponse(
            content="Please provide a valid, non-empty customer ID.",
        ),
    ])

    runner = AgentRunner(model=mock_model)
    result = runner.execute("Look up customer", default_context)

    assert result.is_success
    assert len(result.tool_executions) == 1
    assert result.tool_executions[0]["status"] == "failed"
    assert "validation" in result.tool_executions[0]["error_message"].lower()


# ---------------------------------------------------------------------------
# 5. Acceptance Criterion: Unauthorized tool calls never execute
# ---------------------------------------------------------------------------


def test_unauthorized_tool_call_for_read_only_principal():
    read_only_context = PrincipalContext(
        tenant_id="tenant-alpha",
        user_id="user-viewer",
        role="read_only",  # Read-only role cannot mutate
        allowed_tools={"lookup_customer", "schedule_callback"},
    )

    mock_model = MockScriptedModelAdapter([
        # Step 1: Model attempts side-effecting callback tool
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_mut",
                    name="schedule_callback",
                    arguments={
                        "customer_id": "CUST-1001",
                        "callback_time": "2026-10-25T10:00:00Z",
                        "phone_number": "+15551234567",
                        "idempotency_key": "idem-key-001",
                    },
                )
            ],
        ),
        # Step 2: Model reports authorization denial
        ModelResponse(
            content="You do not have write permissions to schedule callbacks.",
        ),
    ])

    runner = AgentRunner(model=mock_model)
    result = runner.execute("Schedule callback", read_only_context)

    assert result.is_success
    assert len(result.tool_executions) == 1
    assert result.tool_executions[0]["status"] == "rejected"
    assert "permission" in result.tool_executions[0]["error_message"].lower()


def test_unassigned_tool_denied(default_context):
    restricted_context = PrincipalContext(
        tenant_id="tenant-alpha",
        user_id="user-123",
        role="agent_operator",
        allowed_tools={"lookup_customer"},  # cancel_reservation is NOT allowed
    )

    mock_model = MockScriptedModelAdapter([
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_cancel",
                    name="cancel_reservation",
                    arguments={
                        "reservation_id": "RES-999",
                        "reason": "Customer change of plans",
                        "idempotency_key": "key-999",
                    },
                )
            ],
        ),
        ModelResponse(content="Action denied: tool not enabled."),
    ])

    runner = AgentRunner(model=mock_model)
    result = runner.execute("Cancel booking", restricted_context)

    assert result.is_success
    assert len(result.tool_executions) == 1
    assert result.tool_executions[0]["status"] == "rejected"
    assert "not authorized" in result.tool_executions[0]["error_message"].lower()


# ---------------------------------------------------------------------------
# 6. Acceptance Criterion: Consequential actions require explicit confirmation
# ---------------------------------------------------------------------------


def test_consequential_tool_requires_explicit_confirmation(default_context):
    mock_model = MockScriptedModelAdapter([
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_cancel",
                    name="cancel_reservation",
                    arguments={
                        "reservation_id": "RES-888",
                        "reason": "Flight delayed",
                        "idempotency_key": "idem-cancel-888",
                    },
                )
            ],
        )
    ])

    runner = AgentRunner(model=mock_model)
    # Context does NOT have 'idem-cancel-888' in confirmed_actions
    result = runner.execute("Cancel my reservation RES-888", default_context)

    assert result.status == "confirmation_required"
    assert result.pending_confirmation is not None
    assert result.pending_confirmation["tool_name"] == "cancel_reservation"
    assert result.pending_confirmation["action_id"] == "idem-cancel-888"

    # Now verify that providing confirmed_action allows execution
    confirmed_context = PrincipalContext(
        tenant_id="tenant-alpha",
        user_id="user-123",
        role="agent_operator",
        allowed_tools=default_context.allowed_tools,
        confirmed_actions={"idem-cancel-888"},
    )
    mock_model_confirmed = MockScriptedModelAdapter([
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_cancel_2",
                    name="cancel_reservation",
                    arguments={
                        "reservation_id": "RES-888",
                        "reason": "Flight delayed",
                        "idempotency_key": "idem-cancel-888",
                    },
                )
            ],
        ),
        ModelResponse(content="Reservation RES-888 was successfully cancelled."),
    ])

    runner2 = AgentRunner(model=mock_model_confirmed)
    result2 = runner2.execute("Confirm cancellation of RES-888", confirmed_context)

    assert result2.is_success
    assert result2.status == "completed"
    assert result2.tool_executions[0]["status"] == "completed"
    assert result2.tool_executions[0]["result"]["status"] == "CANCELLED"


# ---------------------------------------------------------------------------
# 7. Acceptance Criterion: Infinite tool loops are prevented
# ---------------------------------------------------------------------------


def test_infinite_tool_loop_prevented(default_context):
    # Model keeps invoking lookup_customer continuously without ever returning text
    loop_responses = [
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"call_{i}",
                    name="lookup_customer",
                    arguments={"customer_id": f"CUST-{i}"},
                )
            ],
        )
        for i in range(10)
    ]
    mock_model = MockScriptedModelAdapter(loop_responses)

    config = AgentConfig(max_steps=3)  # Hard bound of 3 steps
    runner = AgentRunner(agent_config=config, model=mock_model)
    result = runner.execute("Looping request", default_context)

    assert result.status == "max_steps_exceeded"
    assert result.steps_taken == 3
    assert "unable to complete the request within the permitted execution steps" in result.output_text


# ---------------------------------------------------------------------------
# 8. Acceptance Criterion: Provider errors do not crash the API process
# ---------------------------------------------------------------------------


def test_provider_errors_do_not_crash_api(default_context):
    mock_model = MockScriptedModelAdapter([
        ModelProviderError("Gemini 503 Service Unavailable: Overloaded")
    ])

    runner = AgentRunner(model=mock_model)
    result = runner.execute("Hello Gemini", default_context)

    # Must fail gracefully and report error without raising uncaught exception
    assert result.status == "provider_error"
    assert "language model provider encountered an error" in result.output_text
    assert "503 Service Unavailable" in (result.error_message or "")


def test_provider_timeout_does_not_crash_api(default_context):
    mock_model = MockScriptedModelAdapter([
        ModelTimeoutError("Gemini request timed out after 30s")
    ])

    runner = AgentRunner(model=mock_model)
    result = runner.execute("Long prompt", default_context)

    assert result.status == "provider_error"
    assert "timed out" in (result.error_message or "")


# ---------------------------------------------------------------------------
# 9. Tenant Isolation & Security Claims
# ---------------------------------------------------------------------------


def test_model_generated_tenant_spoofing_is_rejected(default_context):
    # Model attempts to pass a different tenant_id in arguments
    policy = PolicyEngine()
    auth_res = policy.authorize_tool(
        tool_name="lookup_customer",
        is_side_effecting=False,
        requires_confirmation=False,
        context=default_context,  # tenant-alpha
        arguments={"customer_id": "CUST-1", "tenant_id": "malicious-tenant-beta"},
    )
    assert auth_res.status == AuthorizationStatus.DENIED
    assert "spoofing" in auth_res.reason.lower() or "tenant" in auth_res.reason.lower()


def test_idempotency_prevents_duplicate_side_effect(default_context):
    call_records = []

    def counting_callback_handler(ctx, data):
        call_records.append(data.idempotency_key)
        return CancelReservationOutput(
            reservation_id=data.reservation_id,
            status="CANCELLED",
            refund_eligible=True,
            message="Cancelled",
            idempotency_key=data.idempotency_key,
        )

    custom_registry = ToolRegistry()
    custom_registry.register(
        Tool(
            name="cancel_reservation",
            description="Cancel reservation",
            input_schema=CancelReservationInput,
            output_schema=CancelReservationOutput,
            handler=counting_callback_handler,
            requires_confirmation=False,
            is_side_effecting=True,
        )
    )

    mock_model = MockScriptedModelAdapter([
        # Turn 1: cancel
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="cancel_reservation",
                    arguments={
                        "reservation_id": "RES-1",
                        "reason": "Change of plans",
                        "idempotency_key": "IDEM-REPEAT-KEY",
                    },
                )
            ],
        ),
        # Turn 2: model attempts exact same tool call again in the same orchestration
        ModelResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="c2",
                    name="cancel_reservation",
                    arguments={
                        "reservation_id": "RES-1",
                        "reason": "Change of plans",
                        "idempotency_key": "IDEM-REPEAT-KEY",
                    },
                )
            ],
        ),
        ModelResponse(content="Done"),
    ])

    runner = AgentRunner(model=mock_model, registry=custom_registry)
    result = runner.execute("Cancel twice", default_context)

    assert result.is_success
    # Handler should only have been called ONCE due to idempotency cache hit
    assert len(call_records) == 1
    assert len(result.tool_executions) == 2
    assert result.tool_executions[1]["duration_ms"] == 0  # Cached hit


# ---------------------------------------------------------------------------
# 10. Audit and Usage Event Hooks
# ---------------------------------------------------------------------------


def test_audit_and_usage_hooks_emitted(default_context):
    usage_events = []
    audit_events = []

    def on_usage(event_type, quantity, unit, meta):
        usage_events.append((event_type, quantity, unit, meta))

    def on_audit(action, entity_type, entity_id, outcome, details):
        audit_events.append((action, entity_type, entity_id, outcome, details))

    mock_model = MockScriptedModelAdapter([
        ModelResponse(
            content="Response text",
            usage=UsageTokens(prompt_tokens=25, response_tokens=15, total_tokens=40),
        )
    ])

    runner = AgentRunner(
        model=mock_model,
        on_usage_hook=on_usage,
        on_audit_hook=on_audit,
    )
    res = runner.execute("Audit test", default_context)

    assert res.is_success
    assert len(usage_events) == 1
    assert usage_events[0][0] == "llm_tokens"
    assert usage_events[0][1] == 40

    assert len(audit_events) == 1
    assert audit_events[0][0] == "agent_orchestration_run"
    assert audit_events[0][3] == "SUCCESS"


# ---------------------------------------------------------------------------
# 11. Bounded Conversation Memory Sliding Window
# ---------------------------------------------------------------------------


def test_bounded_conversation_memory_window():
    memory = ConversationMemory(system_instruction="System prompt", max_turns=4)
    # Add 6 user/model turns
    memory.add_user_message("Query 1")
    memory.add_model_message("Reply 1")
    memory.add_user_message("Query 2")
    memory.add_model_message("Reply 2")
    memory.add_user_message("Query 3")
    memory.add_model_message("Reply 3")

    bounded = memory.get_bounded_turns()
    # max_turns=4: retains first turn + last 3 turns
    assert len(bounded) == 4
    assert bounded[0].content == "Query 1"
    assert bounded[-1].content == "Reply 3"


# ---------------------------------------------------------------------------
# 12. Sensitive Data Redaction
# ---------------------------------------------------------------------------


def test_sensitive_key_redaction():
    text_with_keys = "Error connecting with key=AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q and token=secret_token_123"
    sanitized = redact_sensitive(text_with_keys)

    assert "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q" not in sanitized
    assert "secret_token_123" not in sanitized
    assert "REDACTED" in sanitized

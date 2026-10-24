"""Base protocols, dataclasses and exceptions for model adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ModelAdapterError(Exception):
    """Base exception for model adapter failures."""


class ModelProviderError(ModelAdapterError):
    """Raised when the underlying model provider returns an API error or is unreachable."""


class ModelTimeoutError(ModelProviderError):
    """Raised when a model generation request times out."""


@dataclass(frozen=True)
class ToolCall:
    """Structured representation of a function/tool request emitted by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsageTokens:
    """Metered token count for billing and rate-limiting."""

    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ModelResponse:
    """Standardized response from any model adapter."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: UsageTokens = field(default_factory=UsageTokens)
    raw_response: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class ModelAdapter(Protocol):
    """Protocol satisfied by all LLM model adapters."""

    def generate(
        self,
        contents: list[Any],
        *,
        system_instruction: str | None = None,
        tools: list[Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> ModelResponse:
        """Send contents and tools to the model and receive a structured ModelResponse."""
        ...

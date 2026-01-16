"""Base provider interface for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planify.config import ProviderConfig


class Role(str, Enum):
    """Message role."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """A single message in a conversation."""

    role: Role
    content: str

    def to_dict(self) -> dict:
        """Convert to dictionary for API calls."""
        return {"role": self.role.value, "content": self.content}


@dataclass
class ProviderResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    finish_reason: str = "stop"

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens


@dataclass
class UsageStats:
    """Accumulated usage statistics."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0

    def add(self, response: ProviderResponse) -> None:
        """Add response stats to totals."""
        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens
        self.total_cost_usd += response.cost_usd
        self.call_count += 1


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: ProviderConfig):
        """Initialize the provider with configuration."""
        self.config = config
        self.usage = UsageStats()

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'openai', 'anthropic')."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> ProviderResponse:
        """Send a completion request to the provider.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt to prepend

        Returns:
            ProviderResponse with the completion

        Raises:
            ProviderError: If the API call fails
        """
        ...

    @abstractmethod
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        ...

    def reset_usage(self) -> None:
        """Reset usage statistics."""
        self.usage = UsageStats()


class ProviderError(Exception):
    """Error from an LLM provider."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable

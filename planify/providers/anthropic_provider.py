"""Anthropic (Claude) provider for Planify."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from anthropic import AsyncAnthropic, APIError, APIConnectionError, RateLimitError

from planify.providers.base import (
    LLMProvider,
    Message,
    ProviderError,
    ProviderResponse,
    Role,
)

if TYPE_CHECKING:
    from planify.config import ProviderConfig

# Pricing per 1M tokens (as of Jan 2025)
# https://www.anthropic.com/pricing
ANTHROPIC_PRICING = {
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}


class AnthropicProvider(LLMProvider):
    """Anthropic API provider for Claude models."""

    def __init__(self, config: ProviderConfig):
        """Initialize the Anthropic provider.

        Args:
            config: Provider configuration

        Raises:
            ProviderError: If ANTHROPIC_API_KEY is not set
        """
        super().__init__(config)

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ProviderError(
                "ANTHROPIC_API_KEY environment variable is not set",
                provider="anthropic",
            )

        self.client = AsyncAnthropic(api_key=api_key)

    @property
    def name(self) -> str:
        """Provider name."""
        return "anthropic"

    async def complete(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> ProviderResponse:
        """Send a completion request to Anthropic.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt

        Returns:
            ProviderResponse with the completion

        Raises:
            ProviderError: If the API call fails
        """
        # Convert messages to Anthropic format
        # Anthropic doesn't use a system role in messages - it's a separate parameter
        api_messages = []

        for msg in messages:
            if msg.role == Role.SYSTEM:
                # Skip system messages in the messages list
                # They should be passed via system_prompt parameter
                continue
            api_messages.append({"role": msg.role.value, "content": msg.content})

        try:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system_prompt or "",
                messages=api_messages,
            )

            # Extract response data
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = self.calculate_cost(input_tokens, output_tokens)

            result = ProviderResponse(
                content=content,
                model=response.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                finish_reason=response.stop_reason or "end_turn",
            )

            # Track usage
            self.usage.add(result)

            return result

        except RateLimitError as e:
            raise ProviderError(
                f"Anthropic rate limit exceeded: {e}",
                provider="anthropic",
                status_code=429,
                retryable=True,
            ) from e
        except APIConnectionError as e:
            raise ProviderError(
                f"Anthropic connection error: {e}",
                provider="anthropic",
                retryable=True,
            ) from e
        except APIError as e:
            raise ProviderError(
                f"Anthropic API error: {e}",
                provider="anthropic",
                status_code=getattr(e, "status_code", None),
                retryable=False,
            ) from e

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        model = self.config.model

        # Get pricing for model (fallback to sonnet pricing)
        pricing = ANTHROPIC_PRICING.get(
            model, ANTHROPIC_PRICING["claude-sonnet-4-20250514"]
        )

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

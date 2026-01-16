"""OpenAI provider for Planify."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

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
# https://openai.com/pricing
OPENAI_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self, config: ProviderConfig):
        """Initialize the OpenAI provider.

        Args:
            config: Provider configuration

        Raises:
            ProviderError: If OPENAI_API_KEY is not set
        """
        super().__init__(config)

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError(
                "OPENAI_API_KEY environment variable is not set",
                provider="openai",
            )

        self.client = AsyncOpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        """Provider name."""
        return "openai"

    async def complete(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> ProviderResponse:
        """Send a completion request to OpenAI.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt to prepend

        Returns:
            ProviderResponse with the completion

        Raises:
            ProviderError: If the API call fails
        """
        # Build messages list
        api_messages = []

        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            api_messages.append(msg.to_dict())

        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=api_messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            # Extract response data
            choice = response.choices[0]
            content = choice.message.content or ""
            usage = response.usage

            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            cost = self.calculate_cost(input_tokens, output_tokens)

            result = ProviderResponse(
                content=content,
                model=response.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                finish_reason=choice.finish_reason or "stop",
            )

            # Track usage
            self.usage.add(result)

            return result

        except RateLimitError as e:
            raise ProviderError(
                f"OpenAI rate limit exceeded: {e}",
                provider="openai",
                status_code=429,
                retryable=True,
            ) from e
        except APIConnectionError as e:
            raise ProviderError(
                f"OpenAI connection error: {e}",
                provider="openai",
                retryable=True,
            ) from e
        except APIError as e:
            raise ProviderError(
                f"OpenAI API error: {e}",
                provider="openai",
                status_code=e.status_code,
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

        # Get pricing for model (fallback to gpt-4o pricing)
        pricing = OPENAI_PRICING.get(model, OPENAI_PRICING["gpt-4o"])

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

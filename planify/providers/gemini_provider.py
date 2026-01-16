"""Google Gemini provider for Planify."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx

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
# https://ai.google.dev/pricing
GEMINI_PRICING = {
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15},
    "gemini-2.0-flash-exp": {"input": 0.0, "output": 0.0},  # Free during preview
    "gemini-pro": {"input": 0.50, "output": 1.50},
}

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    """Google Gemini API provider."""

    def __init__(self, config: ProviderConfig):
        """Initialize the Gemini provider.

        Args:
            config: Provider configuration

        Raises:
            ProviderError: If GEMINI_API_KEY is not set
        """
        super().__init__(config)

        self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ProviderError(
                "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is not set",
                provider="gemini",
            )

        self.client = httpx.AsyncClient(timeout=120.0)

    @property
    def name(self) -> str:
        """Provider name."""
        return "gemini"

    async def complete(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> ProviderResponse:
        """Send a completion request to Gemini.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt

        Returns:
            ProviderResponse with the completion

        Raises:
            ProviderError: If the API call fails
        """
        # Build Gemini format contents
        contents = []

        # Add system prompt as first user message if provided
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"System Instructions:\n{system_prompt}\n\nPlease acknowledge and follow these instructions."}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "I understand and will follow these instructions."}]
            })

        # Convert messages
        for msg in messages:
            role = "user" if msg.role in (Role.USER, Role.SYSTEM) else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.content}]
            })

        # Build request
        url = f"{GEMINI_API_URL}/{self.config.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
            }
        }

        try:
            response = await self.client.post(url, json=payload)

            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", response.text)
                raise ProviderError(
                    f"Gemini API error: {error_msg}",
                    provider="gemini",
                    status_code=response.status_code,
                    retryable=response.status_code in (429, 500, 503),
                )

            data = response.json()

            # Extract response
            candidates = data.get("candidates", [])
            if not candidates:
                raise ProviderError(
                    "Gemini returned no candidates",
                    provider="gemini",
                )

            content = ""
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    content += part["text"]

            # Extract usage metadata
            usage = data.get("usageMetadata", {})
            input_tokens = usage.get("promptTokenCount", 0)
            output_tokens = usage.get("candidatesTokenCount", 0)

            cost = self.calculate_cost(input_tokens, output_tokens)

            result = ProviderResponse(
                content=content,
                model=self.config.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                finish_reason=candidates[0].get("finishReason", "STOP"),
            )

            # Track usage
            self.usage.add(result)

            return result

        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Gemini request timed out: {e}",
                provider="gemini",
                retryable=True,
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(
                f"Gemini connection error: {e}",
                provider="gemini",
                retryable=True,
            ) from e

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for token usage."""
        model = self.config.model
        pricing = GEMINI_PRICING.get(model, GEMINI_PRICING.get("gemini-1.5-flash", {"input": 0.075, "output": 0.30}))

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

"""Base agent class for planning agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from planify.providers.base import LLMProvider, Message, Role, ProviderResponse

if TYPE_CHECKING:
    from planify.context import LoadedContext


@dataclass
class AgentResponse:
    """Response from an agent."""

    content: str
    phase: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class Agent(ABC):
    """Base class for planning agents."""

    def __init__(self, provider: LLMProvider):
        """Initialize the agent.

        Args:
            provider: LLM provider to use for completions
        """
        self.provider = provider

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name (e.g., 'architect', 'critic')."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for this agent."""
        ...

    async def run(
        self,
        task: str,
        context: LoadedContext,
        conversation_history: list[AgentResponse] | None = None,
    ) -> AgentResponse:
        """Run the agent on a task.

        Args:
            task: The task description
            context: Project context
            conversation_history: Previous agent responses in this planning session

        Returns:
            AgentResponse with the agent's output
        """
        # Build the user message
        user_content = self._build_user_message(task, context, conversation_history)

        messages = [Message(role=Role.USER, content=user_content)]

        # Call the provider
        response = await self.provider.complete(
            messages=messages,
            system_prompt=self.system_prompt,
        )

        return AgentResponse(
            content=response.content,
            phase=self.name,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
        )

    def _build_user_message(
        self,
        task: str,
        context: LoadedContext,
        conversation_history: list[AgentResponse] | None,
    ) -> str:
        """Build the user message for the agent.

        Args:
            task: The task description
            context: Project context
            conversation_history: Previous agent responses

        Returns:
            Formatted user message
        """
        parts = []

        # Add project context
        if context.files:
            parts.append(context.to_prompt())
            parts.append("\n---\n\n")

        # Add task
        parts.append(f"# Task\n\n{task}\n\n")

        # Add conversation history if present
        if conversation_history:
            parts.append("# Previous Planning Discussion\n\n")
            for response in conversation_history:
                parts.append(f"## {response.phase.title()}\n\n")
                parts.append(response.content)
                parts.append("\n\n")
            parts.append("---\n\n")

        # Add agent-specific instructions
        parts.append(self._get_task_instructions())

        return "".join(parts)

    @abstractmethod
    def _get_task_instructions(self) -> str:
        """Get agent-specific task instructions.

        Returns:
            Instructions to append to the user message
        """
        ...

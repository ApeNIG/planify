"""Orchestrator - manages the multi-agent planning conversation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Awaitable

from planify.agents import (
    Agent,
    AgentResponse,
    ArchitectAgent,
    CriticAgent,
    IntegratorAgent,
)
from planify.config import PlanifyConfig
from planify.context import ContextLoader, LoadedContext, parse_doc_architecture
from planify.output.doc_impact import (
    DocImpactAnalysis,
    analyze_plan_impact,
    render_doc_impacts_markdown,
)
from planify.providers import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
    ProviderError,
)


class Phase(str, Enum):
    """Planning phases."""

    ARCHITECT = "architect"
    CRITIC = "critic"
    REBUTTAL = "rebuttal"
    INTEGRATOR = "integrator"


class SessionStatus(str, Enum):
    """Session status."""

    IN_PROGRESS = "in_progress"
    AWAITING_FEEDBACK = "awaiting_feedback"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""

    phase: str
    model: str
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    human_feedback: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ConversationTurn:
        return cls(**data)


@dataclass
class Session:
    """A planning session."""

    id: str
    task: str
    repo_path: str
    status: SessionStatus = SessionStatus.IN_PROGRESS
    current_phase: Phase = Phase.ARCHITECT
    round: int = 1
    conversation: list[ConversationTurn] = field(default_factory=list)
    total_cost_usd: float = 0.0
    files_loaded: list[str] = field(default_factory=list)
    tokens_used: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # Doc-aware planning: analysis of which docs need updating
    doc_impact_analysis: dict | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "repo_path": self.repo_path,
            "status": self.status.value,
            "current_phase": self.current_phase.value,
            "round": self.round,
            "conversation": [t.to_dict() for t in self.conversation],
            "total_cost_usd": self.total_cost_usd,
            "files_loaded": self.files_loaded,
            "tokens_used": self.tokens_used,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "doc_impact_analysis": self.doc_impact_analysis,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        return cls(
            id=data["id"],
            task=data["task"],
            repo_path=data["repo_path"],
            status=SessionStatus(data["status"]),
            current_phase=Phase(data["current_phase"]),
            round=data["round"],
            conversation=[
                ConversationTurn.from_dict(t) for t in data["conversation"]
            ],
            total_cost_usd=data["total_cost_usd"],
            files_loaded=data["files_loaded"],
            tokens_used=data["tokens_used"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            doc_impact_analysis=data.get("doc_impact_analysis"),
        )

    def save(self, session_dir: Path) -> Path:
        """Save session to disk."""
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"{self.id}.json"
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path

    @classmethod
    def load(cls, path: Path) -> Session:
        """Load session from disk."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


# Type for human feedback callback
FeedbackCallback = Callable[[str, AgentResponse], Awaitable[str | None]]


class Orchestrator:
    """Orchestrates the multi-agent planning conversation."""

    def __init__(self, config: PlanifyConfig):
        """Initialize the orchestrator.

        Args:
            config: Planify configuration
        """
        self.config = config
        self._providers: dict[str, LLMProvider] = {}
        self._agents: dict[str, Agent] = {}

    def _get_provider(self, provider_name: str) -> LLMProvider:
        """Get or create a provider instance.

        Args:
            provider_name: Name of the provider ('openai', 'anthropic', or 'gemini')

        Returns:
            LLMProvider instance
        """
        if provider_name not in self._providers:
            provider_config = self.config.get_provider_config(provider_name)

            if provider_name == "openai":
                self._providers[provider_name] = OpenAIProvider(provider_config)
            elif provider_name == "anthropic":
                self._providers[provider_name] = AnthropicProvider(provider_config)
            elif provider_name == "gemini":
                self._providers[provider_name] = GeminiProvider(provider_config)
            else:
                raise ValueError(f"Unknown provider: {provider_name}")

        return self._providers[provider_name]

    def _get_agent(self, role: str) -> Agent:
        """Get or create an agent instance.

        Args:
            role: Agent role ('architect', 'critic', 'integrator')

        Returns:
            Agent instance
        """
        if role not in self._agents:
            provider_name = self.config.get_provider_for_role(role)
            provider = self._get_provider(provider_name)

            if role == "architect":
                self._agents[role] = ArchitectAgent(provider)
            elif role == "critic":
                self._agents[role] = CriticAgent(provider)
            elif role == "integrator":
                self._agents[role] = IntegratorAgent(provider)
            else:
                raise ValueError(f"Unknown role: {role}")

        return self._agents[role]

    async def run(
        self,
        task: str,
        repo_path: Path,
        feedback_callback: FeedbackCallback | None = None,
        session: Session | None = None,
    ) -> Session:
        """Run a planning session.

        Args:
            task: The task to plan
            repo_path: Path to the repository
            feedback_callback: Async callback for human feedback after each phase.
                               Called with (phase_name, agent_response).
                               Return feedback string or None to continue.
            session: Existing session to resume (optional)

        Returns:
            Completed Session
        """
        # Load context
        loader = ContextLoader(self.config.context)
        context = loader.load(repo_path)

        # Parse doc architecture for doc-aware planning
        doc_arch = parse_doc_architecture(context)

        # Create or resume session
        if session is None:
            session = self._create_session(task, repo_path, context)
        else:
            # Update context for resumed session
            session.files_loaded = [str(f.path) for f in context.files]
            session.tokens_used = context.total_tokens

        # Run the planning loop
        try:
            await self._run_loop(session, context, feedback_callback)
        except ProviderError as e:
            session.status = SessionStatus.ABORTED
            raise

        # Analyze doc impact if planning completed successfully
        if session.status == SessionStatus.COMPLETED and doc_arch.routing_table:
            final_plan = self._extract_final_plan(session)
            impact_analysis = analyze_plan_impact(final_plan, doc_arch, task)
            session.doc_impact_analysis = impact_analysis.to_dict()

        return session

    def _extract_final_plan(self, session: Session) -> str:
        """Extract the final plan content from the session."""
        # Look for the last integrator turn
        for turn in reversed(session.conversation):
            if turn.phase == "integrator":
                return turn.content

        # Fall back to last architect turn
        for turn in reversed(session.conversation):
            if turn.phase == "architect":
                return turn.content

        # Fall back to last turn
        if session.conversation:
            return session.conversation[-1].content

        return ""

    def _create_session(
        self,
        task: str,
        repo_path: Path,
        context: LoadedContext,
    ) -> Session:
        """Create a new planning session."""
        # Generate session ID from timestamp and task slug
        timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
        slug = self._slugify(task)
        session_id = f"{timestamp}-{slug}"

        return Session(
            id=session_id,
            task=task,
            repo_path=str(repo_path),
            files_loaded=[str(f.path) for f in context.files],
            tokens_used=context.total_tokens,
        )

    async def _run_loop(
        self,
        session: Session,
        context: LoadedContext,
        feedback_callback: FeedbackCallback | None,
    ) -> None:
        """Run the main planning loop."""
        max_rounds = self.config.limits.max_rounds
        max_cost = self.config.limits.max_total_cost

        while session.round <= max_rounds:
            # Check cost limit
            if session.total_cost_usd >= max_cost:
                session.status = SessionStatus.ABORTED
                raise ProviderError(
                    f"Cost limit exceeded: ${session.total_cost_usd:.2f} >= ${max_cost:.2f}",
                    provider="orchestrator",
                )

            # Run current phase
            phase = session.current_phase
            agent = self._get_agent(
                "architect" if phase == Phase.REBUTTAL else phase.value
            )

            # Build conversation history for agent
            history = [
                AgentResponse(
                    content=t.content,
                    phase=t.phase,
                    model=t.model,
                    input_tokens=t.input_tokens,
                    output_tokens=t.output_tokens,
                    cost_usd=t.cost_usd,
                )
                for t in session.conversation
            ]

            # Run the agent
            response = await agent.run(session.task, context, history or None)

            # Record the turn
            turn = ConversationTurn(
                phase=phase.value,
                model=response.model,
                content=response.content,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            )
            session.conversation.append(turn)
            session.total_cost_usd += response.cost_usd
            session.updated_at = datetime.utcnow().isoformat()

            # Get human feedback if callback provided
            if feedback_callback:
                session.status = SessionStatus.AWAITING_FEEDBACK
                feedback = await feedback_callback(phase.value, response)
                turn.human_feedback = feedback
                session.status = SessionStatus.IN_PROGRESS

            # Advance to next phase
            next_phase = self._get_next_phase(phase, session.round, max_rounds)

            if next_phase is None:
                # Planning complete
                session.status = SessionStatus.COMPLETED
                return

            if next_phase == Phase.ARCHITECT and phase == Phase.INTEGRATOR:
                # Starting a new round
                session.round += 1

            session.current_phase = next_phase

    def _get_next_phase(
        self,
        current: Phase,
        current_round: int,
        max_rounds: int,
    ) -> Phase | None:
        """Determine the next phase in the planning cycle.

        Args:
            current: Current phase
            current_round: Current round number
            max_rounds: Maximum rounds allowed

        Returns:
            Next phase, or None if planning is complete
        """
        if current == Phase.ARCHITECT:
            return Phase.CRITIC
        elif current == Phase.CRITIC:
            return Phase.REBUTTAL
        elif current == Phase.REBUTTAL:
            return Phase.INTEGRATOR
        elif current == Phase.INTEGRATOR:
            # After integrator, either start new round or finish
            if current_round < max_rounds:
                return Phase.ARCHITECT
            else:
                return None  # Planning complete

        return None

    def _slugify(self, text: str, max_length: int = 30) -> str:
        """Convert text to a URL-safe slug.

        Args:
            text: Text to slugify
            max_length: Maximum length of slug

        Returns:
            Slugified text
        """
        import re

        # Convert to lowercase
        slug = text.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove non-alphanumeric characters (except hyphens)
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        # Remove multiple consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        # Truncate
        if len(slug) > max_length:
            slug = slug[:max_length].rsplit("-", 1)[0]

        return slug or "plan"

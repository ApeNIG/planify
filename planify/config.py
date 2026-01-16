"""Configuration management for Planify."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    model: str
    temperature: float = 0.3
    max_tokens: int = 4096


class ProvidersConfig(BaseModel):
    """Configuration for all providers."""

    openai: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(model="gpt-4o")
    )
    anthropic: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(model="claude-sonnet-4-20250514")
    )
    gemini: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(model="gemini-1.5-flash")
    )


class RolesConfig(BaseModel):
    """Configuration for agent role assignments."""

    architect: str = "openai"
    critic: str = "anthropic"
    integrator: str = "anthropic"


class LimitsConfig(BaseModel):
    """Configuration for limits and caps."""

    max_rounds: int = 3
    max_tokens_per_turn: int = 4096
    max_total_cost: float = 1.00  # USD
    timeout_seconds: int = 300


class ContextConfig(BaseModel):
    """Configuration for context loading."""

    auto_detect: list[str] = Field(
        default_factory=lambda: [
            "CLAUDE.md",
            "PROJECT_BRIEF.md",
            "ARCHITECTURE.md",
            "README.md",
        ]
    )
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            "**/*.env*",
            "**/node_modules/**",
            "**/.git/**",
            "**/dist/**",
            "**/build/**",
            "**/__pycache__/**",
        ]
    )


class OutputConfig(BaseModel):
    """Configuration for output generation."""

    format: str = "markdown"
    path: str = ".agents/planner/plans/{slug}.md"
    include_transcript: bool = False
    include_cost_summary: bool = True


class PlanifyConfig(BaseModel):
    """Main configuration for Planify."""

    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    roles: RolesConfig = Field(default_factory=RolesConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> PlanifyConfig:
        """Load configuration from file or defaults.

        Looks for config in:
        1. Specified path
        2. ./planify.yaml
        3. ~/.config/planify/config.yaml
        4. Falls back to defaults
        """
        paths_to_try: list[Path] = []

        if config_path:
            paths_to_try.append(config_path)

        paths_to_try.extend(
            [
                Path.cwd() / "planify.yaml",
                Path.cwd() / ".planify.yaml",
                Path.home() / ".config" / "planify" / "config.yaml",
            ]
        )

        for path in paths_to_try:
            if path.exists():
                return cls.from_yaml(path)

        return cls()

    @classmethod
    def from_yaml(cls, path: Path) -> PlanifyConfig:
        """Load configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    def to_yaml(self, path: Path) -> None:
        """Save configuration to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)

    def get_provider_config(self, provider_name: str) -> ProviderConfig:
        """Get configuration for a specific provider."""
        if provider_name == "openai":
            return self.providers.openai
        elif provider_name == "anthropic":
            return self.providers.anthropic
        elif provider_name == "gemini":
            return self.providers.gemini
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def get_provider_for_role(self, role: str) -> str:
        """Get the provider name assigned to a role."""
        if role == "architect":
            return self.roles.architect
        elif role == "critic":
            return self.roles.critic
        elif role == "integrator":
            return self.roles.integrator
        else:
            raise ValueError(f"Unknown role: {role}")

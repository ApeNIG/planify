"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest
import yaml

from planify.config import PlanifyConfig, ProviderConfig, RolesConfig


class TestPlanifyConfig:
    """Tests for PlanifyConfig."""

    def test_default_config(self) -> None:
        config = PlanifyConfig()

        assert config.providers.openai.model == "gpt-4o"
        assert config.providers.anthropic.model == "claude-sonnet-4-20250514"
        assert config.roles.architect == "openai"
        assert config.roles.critic == "anthropic"
        assert config.limits.max_rounds == 3

    def test_load_from_yaml(self) -> None:
        yaml_content = """
providers:
  openai:
    model: gpt-4-turbo
    temperature: 0.5
  anthropic:
    model: claude-3-opus-20240229
    temperature: 0.2

roles:
  architect: anthropic
  critic: openai
  integrator: openai

limits:
  max_rounds: 5
  max_total_cost: 2.00
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            config_path = Path(f.name)

        try:
            config = PlanifyConfig.from_yaml(config_path)

            assert config.providers.openai.model == "gpt-4-turbo"
            assert config.providers.openai.temperature == 0.5
            assert config.providers.anthropic.model == "claude-3-opus-20240229"
            assert config.roles.architect == "anthropic"
            assert config.roles.critic == "openai"
            assert config.limits.max_rounds == 5
            assert config.limits.max_total_cost == 2.00
        finally:
            config_path.unlink()

    def test_get_provider_config(self) -> None:
        config = PlanifyConfig()

        openai_config = config.get_provider_config("openai")
        assert openai_config.model == "gpt-4o"

        anthropic_config = config.get_provider_config("anthropic")
        assert anthropic_config.model == "claude-sonnet-4-20250514"

    def test_get_provider_config_invalid(self) -> None:
        config = PlanifyConfig()

        with pytest.raises(ValueError, match="Unknown provider"):
            config.get_provider_config("invalid")

    def test_get_provider_for_role(self) -> None:
        config = PlanifyConfig()

        assert config.get_provider_for_role("architect") == "openai"
        assert config.get_provider_for_role("critic") == "anthropic"
        assert config.get_provider_for_role("integrator") == "anthropic"

    def test_get_provider_for_role_invalid(self) -> None:
        config = PlanifyConfig()

        with pytest.raises(ValueError, match="Unknown role"):
            config.get_provider_for_role("invalid")

    def test_save_and_load(self) -> None:
        config = PlanifyConfig()
        config.limits.max_rounds = 10

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            config.to_yaml(path)

            loaded = PlanifyConfig.from_yaml(path)

            assert loaded.limits.max_rounds == 10
            assert loaded.providers.openai.model == config.providers.openai.model

    def test_load_fallback_to_defaults(self) -> None:
        # Load from non-existent path should return defaults
        config = PlanifyConfig.load(Path("/nonexistent/path.yaml"))

        assert config.providers.openai.model == "gpt-4o"
        assert config.limits.max_rounds == 3


class TestProviderConfig:
    """Tests for ProviderConfig."""

    def test_defaults(self) -> None:
        config = ProviderConfig(model="test-model")

        assert config.model == "test-model"
        assert config.temperature == 0.3
        assert config.max_tokens == 4096

    def test_custom_values(self) -> None:
        config = ProviderConfig(
            model="test-model",
            temperature=0.7,
            max_tokens=2048,
        )

        assert config.temperature == 0.7
        assert config.max_tokens == 2048

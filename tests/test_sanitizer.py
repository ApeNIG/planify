"""Tests for the secret sanitizer."""

import pytest

from planify.context.sanitizer import SecretSanitizer


class TestSecretSanitizer:
    """Tests for SecretSanitizer."""

    @pytest.fixture
    def sanitizer(self) -> SecretSanitizer:
        return SecretSanitizer()

    def test_sanitizes_openai_key(self, sanitizer: SecretSanitizer) -> None:
        text = "API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456789012345678"
        result = sanitizer.sanitize(text)

        assert "sk-" not in result.text
        assert "[REDACTED:OPENAI_KEY]" in result.text
        assert result.secrets_found == 1
        assert "OPENAI_KEY" in result.patterns_matched

    def test_sanitizes_anthropic_key(self, sanitizer: SecretSanitizer) -> None:
        text = "key = sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = sanitizer.sanitize(text)

        assert "sk-ant-" not in result.text
        assert "[REDACTED:ANTHROPIC_KEY]" in result.text
        assert result.secrets_found == 1

    def test_sanitizes_github_pat(self, sanitizer: SecretSanitizer) -> None:
        text = "GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = sanitizer.sanitize(text)

        assert "ghp_" not in result.text
        assert "[REDACTED:GITHUB_PAT]" in result.text

    def test_sanitizes_bearer_token(self, sanitizer: SecretSanitizer) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.token"
        result = sanitizer.sanitize(text)

        assert "Bearer eyJ" not in result.text
        assert "[REDACTED:BEARER_TOKEN]" in result.text

    def test_sanitizes_database_url(self, sanitizer: SecretSanitizer) -> None:
        text = "DATABASE_URL=postgresql://user:pass@host:5432/db"
        result = sanitizer.sanitize(text)

        assert "postgresql://" not in result.text
        assert "[REDACTED:DATABASE_URL]" in result.text

    def test_sanitizes_multiple_secrets(self, sanitizer: SecretSanitizer) -> None:
        text = """
        OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456789012345678
        GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyz
        """
        result = sanitizer.sanitize(text)

        assert result.secrets_found == 2
        assert "sk-" not in result.text
        assert "ghp_" not in result.text

    def test_leaves_safe_text_unchanged(self, sanitizer: SecretSanitizer) -> None:
        text = "This is safe text without any secrets."
        result = sanitizer.sanitize(text)

        assert result.text == text
        assert result.secrets_found == 0
        assert result.patterns_matched == []

    def test_is_dangerous_file_env(self, sanitizer: SecretSanitizer) -> None:
        assert sanitizer.is_dangerous_file(".env") is True
        assert sanitizer.is_dangerous_file(".env.local") is True
        assert sanitizer.is_dangerous_file(".env.production") is True

    def test_is_dangerous_file_keys(self, sanitizer: SecretSanitizer) -> None:
        assert sanitizer.is_dangerous_file("id_rsa") is True
        assert sanitizer.is_dangerous_file("server.key") is True
        assert sanitizer.is_dangerous_file("cert.pem") is True

    def test_is_safe_file(self, sanitizer: SecretSanitizer) -> None:
        assert sanitizer.is_dangerous_file("README.md") is False
        assert sanitizer.is_dangerous_file("config.yaml") is False
        assert sanitizer.is_dangerous_file("app.py") is False

    def test_scan_for_secrets(self, sanitizer: SecretSanitizer) -> None:
        text = "key = sk-abcdefghijklmnopqrstuvwxyz123456789012345678"
        found = sanitizer.scan_for_secrets(text)

        assert len(found) == 1
        assert found[0][1] == "OPENAI_KEY"

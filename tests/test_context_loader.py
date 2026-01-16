"""Tests for the context loader."""

import tempfile
from pathlib import Path

import pytest

from planify.config import ContextConfig
from planify.context.loader import ContextLoader, LoadedContext


class TestContextLoader:
    """Tests for ContextLoader."""

    @pytest.fixture
    def config(self) -> ContextConfig:
        return ContextConfig(
            auto_detect=["README.md", "CLAUDE.md"],
            include_patterns=[],
            exclude_patterns=["**/*.env*", "**/node_modules/**"],
        )

    @pytest.fixture
    def loader(self, config: ContextConfig) -> ContextLoader:
        return ContextLoader(config, max_tokens=10000, max_file_tokens=1000)

    def test_load_auto_detect_files(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create test files
            (repo / "README.md").write_text("# Test Project")
            (repo / "CLAUDE.md").write_text("Project instructions")
            (repo / "other.txt").write_text("Other content")

            context = loader.load(repo)

            assert len(context.files) == 2
            file_names = [str(f.path) for f in context.files]
            assert "README.md" in file_names
            assert "CLAUDE.md" in file_names
            assert "other.txt" not in file_names

    def test_skips_binary_files(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create test files
            (repo / "README.md").write_text("# Test")
            (repo / "image.png").write_bytes(b"\x89PNG\r\n")

            context = loader.load(repo)

            file_names = [str(f.path) for f in context.files]
            assert "README.md" in file_names
            assert "image.png" not in file_names

    def test_skips_node_modules(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create test structure
            (repo / "README.md").write_text("# Test")
            node_modules = repo / "node_modules" / "package"
            node_modules.mkdir(parents=True)
            (node_modules / "index.js").write_text("module.exports = {}")

            context = loader.load(repo)

            file_paths = [str(f.path) for f in context.files]
            assert not any("node_modules" in p for p in file_paths)

    def test_skips_env_files(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create test files
            (repo / "README.md").write_text("# Test")
            (repo / ".env").write_text("SECRET=value")
            (repo / ".env.local").write_text("LOCAL_SECRET=value")

            context = loader.load(repo)

            file_names = [str(f.path) for f in context.files]
            assert ".env" not in file_names
            assert ".env.local" not in file_names

    def test_sanitizes_secrets(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create file with secrets
            (repo / "README.md").write_text(
                "API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456789012345678"
            )

            context = loader.load(repo)

            assert context.secrets_redacted >= 1
            assert "sk-" not in context.files[0].content

    def test_truncates_large_files(self) -> None:
        config = ContextConfig(auto_detect=["large.txt"])
        loader = ContextLoader(config, max_tokens=10000, max_file_tokens=100)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create large file
            large_content = "word " * 1000  # Much larger than 100 tokens
            (repo / "large.txt").write_text(large_content)

            context = loader.load(repo)

            assert len(context.files) == 1
            assert context.files[0].truncated is True
            assert "[truncated]" in context.files[0].content

    def test_respects_total_token_limit(self) -> None:
        config = ContextConfig(
            auto_detect=["file1.md", "file2.md", "file3.md"]
        )
        loader = ContextLoader(config, max_tokens=200, max_file_tokens=500)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            # Create multiple files
            for i in range(1, 4):
                (repo / f"file{i}.md").write_text("content " * 100)

            context = loader.load(repo)

            # Should not exceed max_tokens
            assert context.total_tokens <= 200

    def test_to_prompt(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)

            (repo / "README.md").write_text("# Test Project")
            (repo / "CLAUDE.md").write_text("Instructions here")

            context = loader.load(repo)
            prompt = context.to_prompt()

            assert "# Project Context" in prompt
            assert "## README.md" in prompt
            assert "# Test Project" in prompt
            assert "## CLAUDE.md" in prompt
            assert "Instructions here" in prompt

    def test_load_single_file(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("Test content")

            result = loader.load_single_file(file_path)

            assert result is not None
            assert result.content == "Test content"
            assert result.truncated is False

    def test_load_single_file_nonexistent(self, loader: ContextLoader) -> None:
        result = loader.load_single_file(Path("/nonexistent/file.txt"))
        assert result is None

    def test_load_single_file_dangerous(self, loader: ContextLoader) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / ".env"
            file_path.write_text("SECRET=value")

            result = loader.load_single_file(file_path)
            assert result is None

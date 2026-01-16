"""Context loading from project files."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from planify.context.sanitizer import SecretSanitizer

if TYPE_CHECKING:
    from planify.config import ContextConfig


class SimpleTokenizer:
    """Simple token estimator (chars / 4 approximation for English text)."""

    def encode(self, text: str) -> list[int]:
        """Estimate tokens (returns dummy list of estimated length)."""
        # Approximate: 1 token ≈ 4 characters for English
        estimated = max(1, len(text) // 4)
        return [0] * estimated

    def decode(self, tokens: list[int]) -> str:
        """Not implemented - not needed for counting."""
        raise NotImplementedError("SimpleTokenizer does not support decode")


@dataclass
class LoadedFile:
    """A single loaded file."""

    path: Path
    content: str
    tokens: int
    truncated: bool = False


@dataclass
class LoadedContext:
    """Loaded context from a project."""

    files: list[LoadedFile] = field(default_factory=list)
    total_tokens: int = 0
    secrets_redacted: int = 0
    files_skipped: list[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        """Convert loaded context to a prompt string."""
        parts = ["# Project Context\n"]

        for file in self.files:
            parts.append(f"## {file.path}\n")
            if file.truncated:
                parts.append("(truncated)\n")
            parts.append("```\n")
            parts.append(file.content)
            parts.append("\n```\n\n")

        return "".join(parts)


class ContextLoader:
    """Load and process context from a project directory."""

    # Binary file extensions to skip
    BINARY_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz", ".rar", ".7z",
        ".exe", ".dll", ".so", ".dylib",
        ".woff", ".woff2", ".ttf", ".eot",
        ".mp3", ".mp4", ".wav", ".avi", ".mov",
        ".sqlite", ".db", ".sqlite3",
        ".pyc", ".pyo", ".class",
        ".lock",  # package-lock.json, yarn.lock, etc.
    }

    # Directories to always skip
    SKIP_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".env",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
    }

    def __init__(
        self,
        config: ContextConfig,
        max_tokens: int = 50000,
        max_file_tokens: int = 5000,
    ):
        """Initialize the context loader.

        Args:
            config: Context configuration
            max_tokens: Maximum total tokens to load
            max_file_tokens: Maximum tokens per file (truncate if exceeded)
        """
        self.config = config
        self.max_tokens = max_tokens
        self.max_file_tokens = max_file_tokens
        self.sanitizer = SecretSanitizer()

        # Use simple token estimation (tiktoken requires Rust compiler on Windows)
        self.encoder = SimpleTokenizer()

    def load(self, repo_path: Path) -> LoadedContext:
        """Load context from a repository.

        Args:
            repo_path: Path to the repository root

        Returns:
            LoadedContext with all loaded files
        """
        context = LoadedContext()
        repo_path = repo_path.resolve()

        # First, load auto-detected files (CLAUDE.md, etc.)
        for filename in self.config.auto_detect:
            file_path = repo_path / filename
            if file_path.exists() and file_path.is_file():
                self._load_file(file_path, repo_path, context)

        # Then load files matching include patterns
        for pattern in self.config.include_patterns:
            for file_path in repo_path.glob(pattern):
                if file_path.is_file():
                    self._load_file(file_path, repo_path, context)

        return context

    def _load_file(
        self,
        file_path: Path,
        repo_path: Path,
        context: LoadedContext,
    ) -> None:
        """Load a single file into context.

        Args:
            file_path: Path to the file
            repo_path: Repository root (for relative paths)
            context: Context to add file to
        """
        relative_path = file_path.relative_to(repo_path)

        # Check if already loaded
        if any(f.path == relative_path for f in context.files):
            return

        # Check if file should be skipped
        if self._should_skip(file_path, relative_path):
            context.files_skipped.append(str(relative_path))
            return

        # Check if we've hit the token limit
        if context.total_tokens >= self.max_tokens:
            context.files_skipped.append(f"{relative_path} (token limit)")
            return

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError) as e:
            context.files_skipped.append(f"{relative_path} ({type(e).__name__})")
            return

        # Sanitize secrets
        result = self.sanitizer.sanitize(content)
        content = result.text
        context.secrets_redacted += result.secrets_found

        # Count tokens
        tokens = len(self.encoder.encode(content))

        # Truncate if too long
        truncated = False
        if tokens > self.max_file_tokens:
            content = self._truncate_to_tokens(content, self.max_file_tokens)
            tokens = self.max_file_tokens
            truncated = True

        # Check if adding this file would exceed total limit
        remaining = self.max_tokens - context.total_tokens
        if tokens > remaining:
            content = self._truncate_to_tokens(content, remaining)
            tokens = remaining
            truncated = True

        context.files.append(
            LoadedFile(
                path=relative_path,
                content=content,
                tokens=tokens,
                truncated=truncated,
            )
        )
        context.total_tokens += tokens

    def _should_skip(self, file_path: Path, relative_path: Path) -> bool:
        """Check if a file should be skipped.

        Args:
            file_path: Absolute path to file
            relative_path: Path relative to repo root

        Returns:
            True if file should be skipped
        """
        # Check binary extensions
        if file_path.suffix.lower() in self.BINARY_EXTENSIONS:
            return True

        # Check if in skipped directory
        for part in relative_path.parts:
            if part in self.SKIP_DIRS:
                return True

        # Check dangerous files
        if self.sanitizer.is_dangerous_file(file_path.name):
            return True

        # Check exclude patterns
        path_str = str(relative_path).replace("\\", "/")
        for pattern in self.config.exclude_patterns:
            if fnmatch.fnmatch(path_str, pattern):
                return True

        return False

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens.

        Args:
            text: Text to truncate
            max_tokens: Maximum tokens

        Returns:
            Truncated text with indicator
        """
        tokens = self.encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text

        # Estimate character count for max_tokens (4 chars per token)
        max_chars = (max_tokens - 10) * 4
        truncated_text = text[:max_chars]

        # Try to break at a line boundary
        last_newline = truncated_text.rfind("\n")
        if last_newline > max_chars // 2:
            truncated_text = truncated_text[:last_newline]

        return truncated_text + "\n\n... [truncated]"

    def load_single_file(self, file_path: Path) -> LoadedFile | None:
        """Load a single file without context.

        Useful for loading specific files the user requests.

        Args:
            file_path: Path to the file

        Returns:
            LoadedFile or None if file can't be loaded
        """
        if not file_path.exists():
            return None

        if self.sanitizer.is_dangerous_file(file_path.name):
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            return None

        result = self.sanitizer.sanitize(content)
        content = result.text
        tokens = len(self.encoder.encode(content))

        truncated = False
        if tokens > self.max_file_tokens:
            content = self._truncate_to_tokens(content, self.max_file_tokens)
            tokens = self.max_file_tokens
            truncated = True

        return LoadedFile(
            path=file_path,
            content=content,
            tokens=tokens,
            truncated=truncated,
        )

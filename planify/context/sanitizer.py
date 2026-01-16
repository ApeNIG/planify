"""Secret sanitization for safe context sharing with LLMs."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SanitizationResult:
    """Result of sanitizing text."""

    text: str
    secrets_found: int
    patterns_matched: list[str]


class SecretSanitizer:
    """Sanitize secrets from text before sending to LLMs."""

    # Patterns for common secrets
    SECRET_PATTERNS = [
        # API keys with common prefixes
        (r"sk-[a-zA-Z0-9]{20,}", "OPENAI_KEY"),
        (r"sk-ant-[a-zA-Z0-9\-]{20,}", "ANTHROPIC_KEY"),
        (r"sk-proj-[a-zA-Z0-9\-]{20,}", "OPENAI_PROJECT_KEY"),
        (r"xoxb-[a-zA-Z0-9\-]+", "SLACK_BOT_TOKEN"),
        (r"xoxp-[a-zA-Z0-9\-]+", "SLACK_USER_TOKEN"),
        (r"ghp_[a-zA-Z0-9]{36}", "GITHUB_PAT"),
        (r"github_pat_[a-zA-Z0-9_]{22,}", "GITHUB_PAT_FINE"),
        (r"gho_[a-zA-Z0-9]{36}", "GITHUB_OAUTH"),
        (r"glpat-[a-zA-Z0-9\-_]{20,}", "GITLAB_PAT"),
        (r"AKIA[0-9A-Z]{16}", "AWS_ACCESS_KEY"),
        (r"AIza[0-9A-Za-z\-_]{35}", "GOOGLE_API_KEY"),
        (r"ya29\.[0-9A-Za-z\-_]+", "GOOGLE_OAUTH_TOKEN"),
        (r"sq0atp-[0-9A-Za-z\-_]{22}", "SQUARE_ACCESS_TOKEN"),
        (r"sq0csp-[0-9A-Za-z\-_]{43}", "SQUARE_OAUTH_SECRET"),
        (r"stripe[_-]?[a-z]+[_-]?[a-zA-Z0-9]{24,}", "STRIPE_KEY"),
        (r"rk_live_[0-9a-zA-Z]{24}", "STRIPE_RESTRICTED_KEY"),
        (r"pk_live_[0-9a-zA-Z]{24}", "STRIPE_PUBLISHABLE_KEY"),
        (r"whsec_[a-zA-Z0-9]{32,}", "STRIPE_WEBHOOK_SECRET"),
        # Bearer tokens
        (r"(?i)bearer\s+[a-zA-Z0-9\-_.]+", "BEARER_TOKEN"),
        # Generic patterns for key-value assignments
        (
            r'(?i)(api[_-]?key|apikey|secret[_-]?key|auth[_-]?token|access[_-]?token|private[_-]?key|client[_-]?secret)\s*[=:]\s*["\']?[a-zA-Z0-9\-_.]{16,}["\']?',
            "GENERIC_SECRET",
        ),
        (
            r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}["\']?',
            "PASSWORD",
        ),
        # Database connection strings
        (
            r"(?i)(postgres|postgresql|mysql|mongodb|redis)://[^\s]+",
            "DATABASE_URL",
        ),
        # JWT tokens (simplified - matches common JWT structure)
        (r"eyJ[a-zA-Z0-9\-_]+\.eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+", "JWT_TOKEN"),
        # Private keys
        (
            r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
            "PRIVATE_KEY_HEADER",
        ),
        # Encryption keys (hex strings of common lengths)
        (r'(?i)(encryption[_-]?key|aes[_-]?key)\s*[=:]\s*["\']?[a-fA-F0-9]{32,}["\']?', "ENCRYPTION_KEY"),
    ]

    # File patterns that should never be loaded
    DANGEROUS_FILE_PATTERNS = [
        r"\.env($|\..*)",
        r"\.env\.local",
        r"\.env\.production",
        r"\.env\.development",
        r"credentials\.json",
        r"service[_-]?account\.json",
        r".*\.pem$",
        r".*\.key$",
        r".*id_rsa.*",
        r".*id_ed25519.*",
        r"\.npmrc$",
        r"\.pypirc$",
        r"\.netrc$",
        r"\.htpasswd$",
    ]

    def __init__(self, replacement_format: str = "[REDACTED:{type}]"):
        """Initialize the sanitizer.

        Args:
            replacement_format: Format string for replacements.
                               Must contain {type} placeholder.
        """
        self.replacement_format = replacement_format
        self._compiled_patterns = [
            (re.compile(pattern), secret_type)
            for pattern, secret_type in self.SECRET_PATTERNS
        ]
        self._dangerous_file_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.DANGEROUS_FILE_PATTERNS
        ]

    def sanitize(self, text: str) -> SanitizationResult:
        """Sanitize secrets from text.

        Args:
            text: Text to sanitize

        Returns:
            SanitizationResult with sanitized text and metadata
        """
        sanitized = text
        secrets_found = 0
        patterns_matched = []

        for pattern, secret_type in self._compiled_patterns:
            matches = pattern.findall(sanitized)
            if matches:
                secrets_found += len(matches)
                patterns_matched.append(secret_type)
                replacement = self.replacement_format.format(type=secret_type)
                sanitized = pattern.sub(replacement, sanitized)

        return SanitizationResult(
            text=sanitized,
            secrets_found=secrets_found,
            patterns_matched=list(set(patterns_matched)),
        )

    def is_dangerous_file(self, filename: str) -> bool:
        """Check if a file should not be loaded due to potential secrets.

        Args:
            filename: Name of the file (not full path)

        Returns:
            True if file should be blocked
        """
        return any(
            pattern.search(filename) for pattern in self._dangerous_file_patterns
        )

    def scan_for_secrets(self, text: str) -> list[tuple[str, str]]:
        """Scan text for secrets without replacing them.

        Useful for warning users about detected secrets.

        Args:
            text: Text to scan

        Returns:
            List of (matched_text, secret_type) tuples
        """
        found = []
        for pattern, secret_type in self._compiled_patterns:
            for match in pattern.finditer(text):
                # Truncate long matches for display
                matched = match.group()
                if len(matched) > 40:
                    matched = matched[:20] + "..." + matched[-10:]
                found.append((matched, secret_type))
        return found

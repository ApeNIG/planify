"""
Doc Architecture Parser for Planify.

Parses CLAUDE.md files to extract routing tables and conventions,
enabling doc-aware planning that automatically identifies which
documentation needs updating based on the plan content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planify.context.loader import LoadedContext


@dataclass
class DocRoute:
    """A single routing rule from CLAUDE.md.

    Maps an area of change to the documentation that owns it.
    """
    area: str           # "Frontend components, routes, E2E tests"
    doc_path: str       # "web/CLAUDE.md"
    keywords: list[str] = field(default_factory=list)  # ["component", "react", "tsx"]

    def matches(self, text: str) -> int:
        """
        Check how well this route matches the given text.

        Args:
            text: Text to match against (e.g., plan content)

        Returns:
            Match score (0 = no match, higher = better match)
        """
        text_lower = text.lower()
        score = 0

        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                score += 1

        return score


@dataclass
class DocArchitecture:
    """Parsed doc architecture for a project.

    Contains the routing table and any conventions extracted
    from CLAUDE.md files.
    """
    root_doc: str | None = None
    routing_table: list[DocRoute] = field(default_factory=list)
    conventions: dict[str, list[str]] = field(default_factory=dict)

    def get_impacted_docs(self, plan_content: str, threshold: int = 2) -> list[tuple[DocRoute, int]]:
        """
        Get docs that would be impacted by the given plan.

        Args:
            plan_content: The plan content to analyze
            threshold: Minimum match score to consider

        Returns:
            List of (route, score) tuples, sorted by score descending
        """
        matches = []

        for route in self.routing_table:
            score = route.matches(plan_content)
            if score >= threshold:
                matches.append((route, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches


# Keyword mappings for common areas
AREA_KEYWORDS = {
    # Frontend
    "frontend": ["component", "react", "tsx", "jsx", "css", "style", "ui", "page", "route", "hook"],
    "component": ["component", "react", "tsx", "jsx", "props", "state", "hook", "render"],
    "e2e": ["test", "playwright", "e2e", "end-to-end", "spec", "fixture"],
    "a11y": ["accessibility", "a11y", "aria", "screen reader", "wcag", "contrast"],

    # Backend
    "backend": ["api", "endpoint", "route", "fastapi", "python", "server", "handler"],
    "api": ["endpoint", "route", "request", "response", "http", "rest", "json"],
    "caching": ["cache", "ttl", "redis", "memcache", "expir"],
    "provider": ["provider", "service", "integration", "external", "client"],

    # Design
    "design": ["color", "theme", "style", "token", "typography", "spacing", "ui"],
    "token": ["color", "font", "spacing", "size", "variable", "css"],
    "contrast": ["contrast", "wcag", "accessibility", "readable"],

    # Safety
    "safety": ["guardrail", "block", "filter", "policy", "security", "sanitize"],
    "security": ["auth", "permission", "token", "secret", "encrypt", "sanitize"],

    # Infrastructure
    "config": ["config", "environment", "env", "setting", "option"],
    "infra": ["docker", "deploy", "ci", "cd", "pipeline", "kubernetes"],
}


def extract_keywords_for_area(area: str) -> list[str]:
    """
    Extract relevant keywords based on area description.

    Args:
        area: Area description from routing table

    Returns:
        List of keywords for matching
    """
    area_lower = area.lower()
    keywords = []

    # Check each keyword category
    for category, category_keywords in AREA_KEYWORDS.items():
        if category in area_lower:
            keywords.extend(category_keywords)

    # Also extract individual words from the area as keywords
    words = re.findall(r'\b[a-z]{3,}\b', area_lower)
    keywords.extend(words)

    # Deduplicate while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    return unique_keywords


def parse_routing_table(content: str) -> list[DocRoute]:
    """
    Parse a routing table from CLAUDE.md content.

    Looks for markdown tables with patterns like:
    | If you're changing... | Update... |
    | Frontend components   | `web/CLAUDE.md` |

    Args:
        content: CLAUDE.md file content

    Returns:
        List of DocRoute objects
    """
    routes = []

    # Find markdown tables - look for rows with pipes
    # Pattern: | cell1 | cell2 | (optional more cells)
    table_row_pattern = r'^\s*\|([^|]+)\|([^|]+)'

    lines = content.split('\n')
    in_routing_table = False

    for i, line in enumerate(lines):
        # Check if this looks like a routing table header
        line_lower = line.lower()
        if 'changing' in line_lower and 'update' in line_lower:
            in_routing_table = True
            continue

        # Skip separator rows (|---|---|)
        if re.match(r'^\s*\|[\s\-:]+\|', line):
            continue

        # Check if we've left the table
        if in_routing_table and not line.strip().startswith('|'):
            in_routing_table = False
            continue

        # Parse table row
        if in_routing_table:
            match = re.match(table_row_pattern, line)
            if match:
                area = match.group(1).strip()
                doc_path = match.group(2).strip()

                # Clean up backticks and extra formatting
                doc_path = doc_path.strip('`').strip()

                # Skip if it looks like a header or separator
                if '---' in area or not doc_path:
                    continue

                # Extract keywords for this area
                keywords = extract_keywords_for_area(area)

                routes.append(DocRoute(
                    area=area,
                    doc_path=doc_path,
                    keywords=keywords,
                ))

    return routes


def parse_conventions(content: str) -> dict[str, list[str]]:
    """
    Extract convention rules from CLAUDE.md content.

    Looks for sections with rules, guidelines, or conventions.

    Args:
        content: CLAUDE.md file content

    Returns:
        Dict mapping convention category to list of rules
    """
    conventions = {}

    # Look for common convention patterns
    # Pattern: "## Something Rules" or "### Guidelines"
    section_pattern = r'^#+\s*(.+?)\s*(?:rules|guidelines|conventions|patterns)\s*$'

    lines = content.split('\n')
    current_section = None
    current_rules = []

    for line in lines:
        # Check for section headers
        header_match = re.match(section_pattern, line, re.IGNORECASE)
        if header_match:
            # Save previous section
            if current_section and current_rules:
                conventions[current_section] = current_rules

            current_section = header_match.group(1).strip().lower()
            current_rules = []
            continue

        # If in a section, look for bullet points or numbered items
        if current_section:
            rule_match = re.match(r'^\s*[-*\d.]+\s+(.+)$', line)
            if rule_match:
                rule = rule_match.group(1).strip()
                if len(rule) > 10:  # Skip very short items
                    current_rules.append(rule)
            elif line.startswith('#'):
                # New section, save current
                if current_rules:
                    conventions[current_section] = current_rules
                current_section = None
                current_rules = []

    # Save last section
    if current_section and current_rules:
        conventions[current_section] = current_rules

    return conventions


def parse_doc_architecture(context: "LoadedContext") -> DocArchitecture:
    """
    Parse doc architecture from loaded context.

    Looks for CLAUDE.md files and extracts routing tables
    and conventions from them.

    Args:
        context: LoadedContext with project files

    Returns:
        DocArchitecture with routing table and conventions
    """
    arch = DocArchitecture()

    for loaded_file in context.files:
        filename = loaded_file.path.name.upper() if hasattr(loaded_file.path, 'name') else str(loaded_file.path).upper()

        # Check if this is a CLAUDE.md file
        if 'CLAUDE.MD' in filename or 'CLAUDE.MD' in str(loaded_file.path).upper():
            content = loaded_file.content

            # Check if this is the root CLAUDE.md
            path_str = str(loaded_file.path)
            if path_str == 'CLAUDE.md' or path_str.endswith('/CLAUDE.md') and path_str.count('/') == 0:
                arch.root_doc = path_str

            # Parse routing table
            routes = parse_routing_table(content)
            arch.routing_table.extend(routes)

            # Parse conventions
            conventions = parse_conventions(content)
            for key, rules in conventions.items():
                if key in arch.conventions:
                    arch.conventions[key].extend(rules)
                else:
                    arch.conventions[key] = rules

    return arch

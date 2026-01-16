"""
Doc Impact Analyzer for Planify.

Analyzes generated plans to determine which documentation
needs to be updated, based on the doc architecture routing table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planify.context.doc_parser import DocArchitecture


class DocImpactPriority(str, Enum):
    """Priority level for doc updates."""

    REQUIRED = "required"       # Strong match - doc definitely needs update
    RECOMMENDED = "recommended" # Moderate match - should probably update
    OPTIONAL = "optional"       # Weak match - consider updating


@dataclass
class DocImpact:
    """A documentation file that needs updating based on the plan."""

    doc_path: str
    area: str
    reason: str
    priority: DocImpactPriority
    match_score: int = 0
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "doc_path": self.doc_path,
            "area": self.area,
            "reason": self.reason,
            "priority": self.priority.value,
            "match_score": self.match_score,
            "matched_keywords": self.matched_keywords,
        }


@dataclass
class DocImpactAnalysis:
    """Complete doc impact analysis for a plan."""

    impacts: list[DocImpact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def required_updates(self) -> list[DocImpact]:
        """Get required doc updates."""
        return [i for i in self.impacts if i.priority == DocImpactPriority.REQUIRED]

    @property
    def recommended_updates(self) -> list[DocImpact]:
        """Get recommended doc updates."""
        return [i for i in self.impacts if i.priority == DocImpactPriority.RECOMMENDED]

    @property
    def optional_updates(self) -> list[DocImpact]:
        """Get optional doc updates."""
        return [i for i in self.impacts if i.priority == DocImpactPriority.OPTIONAL]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "impacts": [i.to_dict() for i in self.impacts],
            "warnings": self.warnings,
        }


def analyze_plan_impact(
    plan_content: str,
    doc_arch: "DocArchitecture",
    task: str = "",
) -> DocImpactAnalysis:
    """
    Analyze a plan to determine which docs need updating.

    Args:
        plan_content: The generated plan content
        doc_arch: Parsed doc architecture with routing table
        task: Original task description (for additional context)

    Returns:
        DocImpactAnalysis with impacts and warnings
    """
    analysis = DocImpactAnalysis()

    # Combine plan and task for analysis
    combined_text = f"{task}\n\n{plan_content}".lower()

    # Track which docs we've already added
    seen_docs = set()

    # Check each route in the doc architecture
    for route in doc_arch.routing_table:
        # Calculate match score
        score = 0
        matched_keywords = []

        for keyword in route.keywords:
            if keyword.lower() in combined_text:
                score += 1
                matched_keywords.append(keyword)

        if score == 0:
            continue

        # Skip if we've already added this doc with a higher score
        if route.doc_path in seen_docs:
            continue

        # Determine priority based on score
        if score >= 4:
            priority = DocImpactPriority.REQUIRED
        elif score >= 2:
            priority = DocImpactPriority.RECOMMENDED
        else:
            priority = DocImpactPriority.OPTIONAL

        # Create impact record
        impact = DocImpact(
            doc_path=route.doc_path,
            area=route.area,
            reason=f"Plan modifies {route.area}",
            priority=priority,
            match_score=score,
            matched_keywords=matched_keywords[:5],  # Limit keywords shown
        )

        analysis.impacts.append(impact)
        seen_docs.add(route.doc_path)

    # Sort by priority (required first) then by score
    priority_order = {
        DocImpactPriority.REQUIRED: 0,
        DocImpactPriority.RECOMMENDED: 1,
        DocImpactPriority.OPTIONAL: 2,
    }
    analysis.impacts.sort(key=lambda i: (priority_order[i.priority], -i.match_score))

    # Add warnings for common issues
    _add_warnings(analysis, plan_content, doc_arch)

    return analysis


def _add_warnings(
    analysis: DocImpactAnalysis,
    plan_content: str,
    doc_arch: "DocArchitecture",
) -> None:
    """
    Add warnings for potential convention violations.

    Args:
        analysis: Analysis to add warnings to
        plan_content: Plan content to check
        doc_arch: Doc architecture with conventions
    """
    plan_lower = plan_content.lower()

    # Check for new API endpoints without docs mention
    if ("endpoint" in plan_lower or "api" in plan_lower) and "route" in plan_lower:
        if "document" not in plan_lower and "docs" not in plan_lower:
            analysis.warnings.append(
                "New API endpoint detected - ensure it's documented in OpenAPI/Swagger"
            )

    # Check for new components without test mention
    if "component" in plan_lower and "tsx" in plan_lower:
        if "test" not in plan_lower:
            analysis.warnings.append(
                "New component detected - consider adding unit tests"
            )

    # Check for environment variable changes
    if "env" in plan_lower and ("variable" in plan_lower or "config" in plan_lower):
        if ".env.example" not in plan_lower:
            analysis.warnings.append(
                "Environment variable changes detected - update .env.example"
            )

    # Check for database/model changes
    if "model" in plan_lower or "schema" in plan_lower or "database" in plan_lower:
        if "migration" not in plan_lower:
            analysis.warnings.append(
                "Data model changes detected - consider if migration is needed"
            )


def render_doc_impacts_markdown(analysis: DocImpactAnalysis) -> str:
    """
    Render doc impacts as markdown for inclusion in plan output.

    Args:
        analysis: Doc impact analysis

    Returns:
        Markdown string
    """
    if not analysis.impacts and not analysis.warnings:
        return "_No documentation updates detected._"

    lines = []

    # Required updates
    required = analysis.required_updates
    if required:
        lines.append("### Required")
        for impact in required:
            keywords = ", ".join(impact.matched_keywords[:3])
            lines.append(f"- [ ] `{impact.doc_path}` — {impact.reason}")
            if keywords:
                lines.append(f"      _Keywords: {keywords}_")

    # Recommended updates
    recommended = analysis.recommended_updates
    if recommended:
        if lines:
            lines.append("")
        lines.append("### Recommended")
        for impact in recommended:
            lines.append(f"- [ ] `{impact.doc_path}` — {impact.reason}")

    # Optional updates (only show if no required/recommended)
    optional = analysis.optional_updates
    if optional and not required and not recommended:
        if lines:
            lines.append("")
        lines.append("### Consider")
        for impact in optional[:3]:  # Limit to 3
            lines.append(f"- [ ] `{impact.doc_path}` — {impact.reason}")

    # Warnings
    if analysis.warnings:
        if lines:
            lines.append("")
        lines.append("### Warnings")
        for warning in analysis.warnings:
            lines.append(f"- ⚠️ {warning}")

    return "\n".join(lines)

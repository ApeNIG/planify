"""Tests for the doc impact analyzer module."""

import pytest
from planify.context.doc_parser import DocRoute, DocArchitecture
from planify.output.doc_impact import (
    DocImpact,
    DocImpactPriority,
    DocImpactAnalysis,
    analyze_plan_impact,
    render_doc_impacts_markdown,
)


class TestDocImpact:
    """Tests for DocImpact class."""

    def test_to_dict(self):
        """Test converting impact to dictionary."""
        impact = DocImpact(
            doc_path="web/CLAUDE.md",
            area="Frontend",
            reason="Plan modifies Frontend",
            priority=DocImpactPriority.REQUIRED,
            match_score=5,
            matched_keywords=["component", "react"],
        )

        result = impact.to_dict()

        assert result["doc_path"] == "web/CLAUDE.md"
        assert result["priority"] == "required"
        assert result["match_score"] == 5


class TestDocImpactAnalysis:
    """Tests for DocImpactAnalysis class."""

    def test_required_updates(self):
        """Test filtering required updates."""
        analysis = DocImpactAnalysis(
            impacts=[
                DocImpact(
                    doc_path="a.md",
                    area="A",
                    reason="R",
                    priority=DocImpactPriority.REQUIRED,
                ),
                DocImpact(
                    doc_path="b.md",
                    area="B",
                    reason="R",
                    priority=DocImpactPriority.RECOMMENDED,
                ),
            ]
        )

        required = analysis.required_updates
        assert len(required) == 1
        assert required[0].doc_path == "a.md"

    def test_to_dict(self):
        """Test converting analysis to dictionary."""
        analysis = DocImpactAnalysis(
            impacts=[
                DocImpact(
                    doc_path="a.md",
                    area="A",
                    reason="R",
                    priority=DocImpactPriority.REQUIRED,
                ),
            ],
            warnings=["Test warning"],
        )

        result = analysis.to_dict()

        assert len(result["impacts"]) == 1
        assert result["warnings"] == ["Test warning"]


class TestAnalyzePlanImpact:
    """Tests for analyze_plan_impact function."""

    def test_analyze_frontend_plan(self):
        """Test analyzing a plan that impacts frontend."""
        doc_arch = DocArchitecture(
            routing_table=[
                DocRoute(
                    area="Frontend components",
                    doc_path="web/CLAUDE.md",
                    keywords=["component", "react", "tsx", "ui", "page"],
                ),
                DocRoute(
                    area="Backend API",
                    doc_path="api/CLAUDE.md",
                    keywords=["endpoint", "api", "route", "fastapi"],
                ),
            ]
        )

        plan = """
        ## Implementation Steps
        1. Create a new React component called PathDiscovery.tsx
        2. Add a page route for /path-discovery
        3. Implement the UI with form inputs
        """

        analysis = analyze_plan_impact(plan, doc_arch)

        # Should identify frontend doc as impacted
        assert len(analysis.impacts) >= 1
        frontend_impact = next(
            (i for i in analysis.impacts if "web" in i.doc_path),
            None
        )
        assert frontend_impact is not None

    def test_analyze_fullstack_plan(self):
        """Test analyzing a plan that impacts both frontend and backend."""
        doc_arch = DocArchitecture(
            routing_table=[
                DocRoute(
                    area="Frontend",
                    doc_path="web/CLAUDE.md",
                    keywords=["component", "react", "tsx"],
                ),
                DocRoute(
                    area="Backend",
                    doc_path="api/CLAUDE.md",
                    keywords=["endpoint", "api", "route"],
                ),
            ]
        )

        plan = """
        1. Create a new React component
        2. Add an API endpoint at /api/data
        3. Connect the component to the route
        """

        analysis = analyze_plan_impact(plan, doc_arch)

        # Should identify both docs as impacted
        doc_paths = [i.doc_path for i in analysis.impacts]
        assert "web/CLAUDE.md" in doc_paths
        assert "api/CLAUDE.md" in doc_paths

    def test_warnings_for_new_endpoint(self):
        """Test that warnings are added for new endpoints."""
        doc_arch = DocArchitecture(routing_table=[])

        plan = """
        Add a new API endpoint at /api/users
        Create the route handler for POST requests
        """

        analysis = analyze_plan_impact(plan, doc_arch)

        # Should have warning about API documentation
        assert any("endpoint" in w.lower() or "api" in w.lower() for w in analysis.warnings)

    def test_warnings_for_new_component(self):
        """Test that warnings are added for new components without tests."""
        doc_arch = DocArchitecture(routing_table=[])

        plan = """
        Create a new UserProfile.tsx component
        Add props for user data
        """

        analysis = analyze_plan_impact(plan, doc_arch)

        # Should have warning about tests
        assert any("test" in w.lower() for w in analysis.warnings)


class TestRenderDocImpactsMarkdown:
    """Tests for render_doc_impacts_markdown function."""

    def test_render_empty_analysis(self):
        """Test rendering empty analysis."""
        analysis = DocImpactAnalysis()

        result = render_doc_impacts_markdown(analysis)

        assert "No documentation updates detected" in result

    def test_render_with_required(self):
        """Test rendering with required updates."""
        analysis = DocImpactAnalysis(
            impacts=[
                DocImpact(
                    doc_path="web/CLAUDE.md",
                    area="Frontend",
                    reason="Plan modifies Frontend",
                    priority=DocImpactPriority.REQUIRED,
                    matched_keywords=["component", "react"],
                ),
            ]
        )

        result = render_doc_impacts_markdown(analysis)

        assert "### Required" in result
        assert "web/CLAUDE.md" in result
        assert "[ ]" in result  # Checkbox

    def test_render_with_warnings(self):
        """Test rendering with warnings."""
        analysis = DocImpactAnalysis(
            warnings=["Update .env.example", "Add unit tests"],
        )

        result = render_doc_impacts_markdown(analysis)

        assert "### Warnings" in result
        assert "⚠️" in result
        assert ".env.example" in result

    def test_render_full_analysis(self):
        """Test rendering full analysis with all sections."""
        analysis = DocImpactAnalysis(
            impacts=[
                DocImpact(
                    doc_path="web/CLAUDE.md",
                    area="Frontend",
                    reason="Plan modifies Frontend",
                    priority=DocImpactPriority.REQUIRED,
                ),
                DocImpact(
                    doc_path="DESIGN_SYSTEM.md",
                    area="Design",
                    reason="Plan modifies Design",
                    priority=DocImpactPriority.RECOMMENDED,
                ),
            ],
            warnings=["Consider adding tests"],
        )

        result = render_doc_impacts_markdown(analysis)

        assert "### Required" in result
        assert "### Recommended" in result
        assert "### Warnings" in result

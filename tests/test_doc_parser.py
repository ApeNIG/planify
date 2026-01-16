"""Tests for the doc parser module."""

import pytest
from planify.context.doc_parser import (
    DocRoute,
    DocArchitecture,
    parse_routing_table,
    parse_conventions,
    extract_keywords_for_area,
)


class TestDocRoute:
    """Tests for DocRoute class."""

    def test_matches_with_keywords(self):
        """Test matching text against route keywords."""
        route = DocRoute(
            area="Frontend components",
            doc_path="web/CLAUDE.md",
            keywords=["component", "react", "tsx"],
        )

        # Should match text containing keywords
        assert route.matches("Create a new React component") >= 2
        assert route.matches("Add a TSX file for the header") >= 1

        # Should not match unrelated text
        assert route.matches("Update the database schema") == 0

    def test_matches_case_insensitive(self):
        """Test that matching is case-insensitive."""
        route = DocRoute(
            area="API endpoints",
            doc_path="api/CLAUDE.md",
            keywords=["endpoint", "api", "route"],
        )

        assert route.matches("Add a new API ENDPOINT") >= 2
        assert route.matches("CREATE A ROUTE handler") >= 1


class TestParseRoutingTable:
    """Tests for parse_routing_table function."""

    def test_parse_simple_table(self):
        """Test parsing a simple routing table."""
        content = """
# When to edit which doc

| If you're changing... | Update... |
|----------------------|-----------|
| Frontend components  | `web/CLAUDE.md` |
| Backend API          | `api/CLAUDE.md` |
| Design tokens        | `DESIGN_SYSTEM.md` |
"""
        routes = parse_routing_table(content)

        assert len(routes) == 3
        assert routes[0].area == "Frontend components"
        assert routes[0].doc_path == "web/CLAUDE.md"
        assert routes[1].area == "Backend API"
        assert routes[1].doc_path == "api/CLAUDE.md"
        assert routes[2].area == "Design tokens"
        assert routes[2].doc_path == "DESIGN_SYSTEM.md"

    def test_parse_table_with_backticks(self):
        """Test parsing table with backticks in paths."""
        content = """
| If you're changing... | Update... |
|----------------------|-----------|
| Safety policy        | `api/app/guardrails.py` + `policy.json` |
"""
        routes = parse_routing_table(content)

        assert len(routes) == 1
        assert "guardrails" in routes[0].doc_path

    def test_keywords_extracted_for_routes(self):
        """Test that keywords are extracted for each route."""
        content = """
| If you're changing... | Update... |
|----------------------|-----------|
| Frontend components, routes, E2E tests | `web/CLAUDE.md` |
"""
        routes = parse_routing_table(content)

        assert len(routes) == 1
        keywords = routes[0].keywords
        # Should have frontend-related keywords
        assert any("component" in kw for kw in keywords)
        assert any("route" in kw for kw in keywords)


class TestExtractKeywords:
    """Tests for extract_keywords_for_area function."""

    def test_frontend_keywords(self):
        """Test extracting keywords for frontend area."""
        keywords = extract_keywords_for_area("Frontend components")

        assert "component" in keywords
        assert "react" in keywords

    def test_backend_keywords(self):
        """Test extracting keywords for backend area."""
        keywords = extract_keywords_for_area("Backend API endpoints")

        assert "api" in keywords
        assert "endpoint" in keywords

    def test_design_keywords(self):
        """Test extracting keywords for design area."""
        keywords = extract_keywords_for_area("Design tokens and colors")

        assert "color" in keywords or "token" in keywords


class TestDocArchitecture:
    """Tests for DocArchitecture class."""

    def test_get_impacted_docs(self):
        """Test finding impacted docs from plan content."""
        arch = DocArchitecture(
            routing_table=[
                DocRoute(
                    area="Frontend",
                    doc_path="web/CLAUDE.md",
                    keywords=["component", "react", "tsx", "ui"],
                ),
                DocRoute(
                    area="Backend",
                    doc_path="api/CLAUDE.md",
                    keywords=["endpoint", "api", "route", "fastapi"],
                ),
            ]
        )

        # Plan that touches frontend
        plan = "Create a new React component for the dashboard UI"
        impacts = arch.get_impacted_docs(plan, threshold=2)

        assert len(impacts) == 1
        assert impacts[0][0].doc_path == "web/CLAUDE.md"

    def test_get_impacted_docs_multiple(self):
        """Test finding multiple impacted docs."""
        arch = DocArchitecture(
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

        # Plan that touches both frontend and backend
        plan = "Create a React component that calls the API endpoint"
        impacts = arch.get_impacted_docs(plan, threshold=1)

        assert len(impacts) == 2


class TestParseConventions:
    """Tests for parse_conventions function."""

    def test_parse_convention_section(self):
        """Test parsing a conventions section."""
        content = """
## Golden Rules

1. Always use TypeScript
2. Test before committing
3. Document public APIs

## Other Section

Some other content here.
"""
        conventions = parse_conventions(content)

        assert "golden" in conventions
        assert len(conventions["golden"]) == 3
        assert "Always use TypeScript" in conventions["golden"]

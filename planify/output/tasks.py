"""Task extraction from generated plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planify.orchestrator import Session


@dataclass
class ExtractedTask:
    """An extracted task from a plan."""

    content: str
    section: str
    completed: bool = False
    priority: int = 0  # Lower is higher priority


class TaskExtractor:
    """Extract actionable tasks from planning session output."""

    # Patterns for task-like items
    TASK_PATTERNS = [
        # Checkbox items: - [ ] task or - [x] task
        (r"^[-*]\s*\[([ xX])\]\s*(.+)$", "checkbox"),
        # Numbered steps: 1. task or 1) task
        (r"^(\d+)[.\)]\s*(.+)$", "numbered"),
    ]

    # Sections that typically contain tasks
    TASK_SECTIONS = [
        "Implementation Steps",
        "Task List",
        "Tasks",
        "Acceptance Criteria",
        "Validation Steps",
        "Next Steps",
        "Action Items",
    ]

    def extract(self, session: "Session") -> list[ExtractedTask]:
        """Extract tasks from a planning session.

        Args:
            session: The planning session

        Returns:
            List of extracted tasks
        """
        # Get the final plan content
        plan = self._get_final_plan(session)

        tasks: list[ExtractedTask] = []
        current_section = "General"
        priority_counter = 0

        for line in plan.split("\n"):
            line = line.strip()

            # Check for section headers
            section_match = re.match(r"^#{1,3}\s*(.+)$", line)
            if section_match:
                section_name = section_match.group(1).strip()
                # Check if this is a task-related section
                for task_section in self.TASK_SECTIONS:
                    if task_section.lower() in section_name.lower():
                        current_section = section_name
                        break
                continue

            # Try to extract task from line
            task = self._extract_task_from_line(line, current_section, priority_counter)
            if task:
                tasks.append(task)
                priority_counter += 1

        return tasks

    def _get_final_plan(self, session: "Session") -> str:
        """Get the final plan from the session."""
        # Look for the last integrator turn
        for turn in reversed(session.conversation):
            if turn.phase == "integrator":
                return turn.content

        # Fall back to last architect turn
        for turn in reversed(session.conversation):
            if turn.phase == "architect":
                return turn.content

        return ""

    def _extract_task_from_line(
        self,
        line: str,
        section: str,
        priority: int,
    ) -> ExtractedTask | None:
        """Try to extract a task from a single line.

        Args:
            line: The line to parse
            section: Current section name
            priority: Priority counter

        Returns:
            ExtractedTask or None
        """
        for pattern, pattern_type in self.TASK_PATTERNS:
            match = re.match(pattern, line)
            if match:
                if pattern_type == "checkbox":
                    completed = match.group(1).lower() == "x"
                    content = match.group(2).strip()
                else:
                    completed = False
                    content = match.group(2).strip()

                # Skip empty or very short tasks
                if len(content) < 5:
                    continue

                return ExtractedTask(
                    content=content,
                    section=section,
                    completed=completed,
                    priority=priority,
                )

        return None

    def to_markdown(self, tasks: list[ExtractedTask]) -> str:
        """Convert extracted tasks to a markdown checklist.

        Args:
            tasks: List of extracted tasks

        Returns:
            Markdown checklist string
        """
        if not tasks:
            return "No tasks extracted."

        lines = ["# Task List\n"]

        # Group by section
        sections: dict[str, list[ExtractedTask]] = {}
        for task in tasks:
            if task.section not in sections:
                sections[task.section] = []
            sections[task.section].append(task)

        # Output by section
        for section, section_tasks in sections.items():
            lines.append(f"\n## {section}\n")
            for task in sorted(section_tasks, key=lambda t: t.priority):
                checkbox = "[x]" if task.completed else "[ ]"
                lines.append(f"- {checkbox} {task.content}")

        return "\n".join(lines)

    def to_json(self, tasks: list[ExtractedTask]) -> list[dict]:
        """Convert extracted tasks to JSON-serializable format.

        Args:
            tasks: List of extracted tasks

        Returns:
            List of task dictionaries
        """
        return [
            {
                "content": task.content,
                "section": task.section,
                "completed": task.completed,
                "priority": task.priority,
            }
            for task in tasks
        ]

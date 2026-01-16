"""Command-line interface for Planify."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table

from planify import __version__
from planify.config import PlanifyConfig
from planify.orchestrator import Orchestrator, Session, Phase
from planify.output import MarkdownGenerator, TaskExtractor
from planify.providers.base import ProviderError

if TYPE_CHECKING:
    from planify.agents import AgentResponse


# Fix Windows console encoding issues
import sys
import os

if sys.platform == "win32":
    # Force UTF-8 encoding on Windows
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

console = Console(force_terminal=True, legacy_windows=False)


def print_banner() -> None:
    """Print the Planify banner."""
    console.print(
        Panel.fit(
            "[bold cyan]Planify[/bold cyan] - Multi-Agent Planning Orchestrator",
            subtitle=f"v{__version__}",
        )
    )


def print_response(phase: str, response: "AgentResponse", verbose: bool = False) -> None:
    """Print an agent response."""
    # Phase header
    phase_colors = {
        "architect": "blue",
        "critic": "yellow",
        "rebuttal": "green",
        "integrator": "magenta",
    }
    color = phase_colors.get(phase, "white")

    console.print(f"\n[bold {color}]{'='*60}[/bold {color}]")
    console.print(f"[bold {color}]{phase.upper()}[/bold {color}] ({response.model})")
    console.print(f"[dim]Cost: ${response.cost_usd:.4f} | Tokens: {response.input_tokens} in / {response.output_tokens} out[/dim]")
    console.print(f"[bold {color}]{'='*60}[/bold {color}]\n")

    # Content as markdown
    console.print(Markdown(response.content))


def get_feedback(phase: str) -> str | None:
    """Get human feedback for a phase."""
    console.print()

    # Ask if user wants to provide feedback
    if not Confirm.ask(
        f"[bold]Provide feedback for {phase}?[/bold]",
        default=False,
    ):
        return None

    # Get feedback
    feedback = Prompt.ask("[bold]Your feedback[/bold]")
    return feedback if feedback.strip() else None


async def async_main(
    task: str,
    repo: Path,
    config_path: Path | None,
    output: Path | None,
    max_rounds: int,
    dry_run: bool,
    verbose: bool,
    resume: Path | None,
    no_interactive: bool,
) -> int:
    """Async main function."""
    # Load config
    config = PlanifyConfig.load(config_path)

    # Override max rounds if specified
    if max_rounds:
        config.limits.max_rounds = max_rounds

    # Check for API keys based on config
    import os

    required_providers = set()
    required_providers.add(config.roles.architect)
    required_providers.add(config.roles.critic)
    required_providers.add(config.roles.integrator)

    missing_keys = []
    if "openai" in required_providers and not os.environ.get("OPENAI_API_KEY"):
        missing_keys.append("OPENAI_API_KEY")
    if "anthropic" in required_providers and not os.environ.get("ANTHROPIC_API_KEY"):
        missing_keys.append("ANTHROPIC_API_KEY")
    if "gemini" in required_providers and not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        missing_keys.append("GEMINI_API_KEY")

    if missing_keys:
        console.print(
            f"[bold red]Error:[/bold red] Missing environment variables: {', '.join(missing_keys)}"
        )
        console.print("\nSet them with:")
        for key in missing_keys:
            console.print(f"  export {key}=your-key-here")
        return 1

    # Load or create session
    session: Session | None = None
    if resume:
        try:
            session = Session.load(resume)
            console.print(f"[green]Resuming session:[/green] {session.id}")
        except Exception as e:
            console.print(f"[red]Failed to load session:[/red] {e}")
            return 1

    # Create orchestrator
    orchestrator = Orchestrator(config)

    # Define feedback callback
    async def feedback_callback(phase: str, response: "AgentResponse") -> str | None:
        print_response(phase, response, verbose)

        if no_interactive:
            return None

        return get_feedback(phase)

    # Session directory
    session_dir = repo / ".planify-session"

    try:
        console.print(f"\n[bold]Task:[/bold] {task}")
        console.print(f"[bold]Repository:[/bold] {repo.resolve()}")
        console.print(f"[bold]Max rounds:[/bold] {config.limits.max_rounds}")
        console.print()

        if dry_run:
            console.print("[yellow]DRY RUN - No actual API calls will be made[/yellow]")
            return 0

        # Run planning
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Starting planning session...", total=None)

            session = await orchestrator.run(
                task=task,
                repo_path=repo,
                feedback_callback=feedback_callback if not no_interactive else None,
                session=session,
            )

        # Save session
        session_path = session.save(session_dir)
        console.print(f"\n[green]Session saved:[/green] {session_path}")

        # Generate output
        generator = MarkdownGenerator()

        if output:
            output_path = generator.save(
                session,
                output,
                include_transcript=verbose,
            )
            console.print(f"[green]Plan saved:[/green] {output_path}")
        else:
            # Print final plan to console
            console.print("\n" + "=" * 60)
            console.print("[bold green]FINAL PLAN[/bold green]")
            console.print("=" * 60 + "\n")
            final_markdown = generator.generate(session, include_transcript=False)
            try:
                console.print(Markdown(final_markdown))
            except (UnicodeEncodeError, OSError):
                # Fallback to plain text if markdown rendering fails
                print(final_markdown)

        # Print summary
        console.print("\n" + "=" * 60)
        console.print("[bold]Summary[/bold]")
        console.print("=" * 60)

        table = Table(show_header=False, box=None)
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Status", session.status.value)
        table.add_row("Rounds", str(session.round))
        table.add_row("Total Cost", f"${session.total_cost_usd:.4f}")
        table.add_row("Files Loaded", str(len(session.files_loaded)))

        console.print(table)

        # Extract and show tasks
        extractor = TaskExtractor()
        tasks = extractor.extract(session)
        if tasks:
            console.print(f"\n[bold]Extracted {len(tasks)} tasks[/bold]")

        return 0

    except ProviderError as e:
        console.print(f"\n[bold red]Provider Error:[/bold red] {e}")
        if session:
            session_path = session.save(session_dir)
            console.print(f"[yellow]Session saved for resume:[/yellow] {session_path}")
        return 1

    except KeyboardInterrupt:
        console.print("\n[yellow]Planning cancelled by user[/yellow]")
        if session:
            session_path = session.save(session_dir)
            console.print(f"[yellow]Session saved for resume:[/yellow] {session_path}")
        return 130


@click.command()
@click.argument("task", required=False)
@click.option(
    "--repo",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository path (default: current directory)",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to planify.yaml config file",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output path for the plan (can use {slug} placeholder)",
)
@click.option(
    "--max-rounds",
    "-m",
    type=int,
    default=0,
    help="Maximum planning rounds (default: from config)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making API calls",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output (include full transcript)",
)
@click.option(
    "--resume",
    type=click.Path(exists=True, path_type=Path),
    help="Resume a previous planning session from JSON file",
)
@click.option(
    "--no-interactive",
    is_flag=True,
    help="Run without human feedback prompts",
)
@click.version_option(version=__version__)
def main(
    task: str | None,
    repo: Path,
    config: Path | None,
    output: Path | None,
    max_rounds: int,
    dry_run: bool,
    verbose: bool,
    resume: Path | None,
    no_interactive: bool,
) -> None:
    """Planify - Multi-Agent Planning Orchestrator

    Run structured AI conversations to plan software features before implementation.

    \b
    Examples:
      planify "Add email notifications" --repo .
      planify "Refactor auth" -r ./myproject -o .agents/planner/plans/auth.md
      planify --resume .planify-session/2024-01-14-auth.json
    """
    print_banner()

    # Validate arguments
    if not task and not resume:
        console.print("[red]Error:[/red] Either TASK or --resume is required")
        console.print("\nUsage: planify TASK [OPTIONS]")
        console.print("       planify --resume SESSION_FILE")
        sys.exit(1)

    # If resuming, task is optional
    if resume and not task:
        task = ""  # Will be loaded from session

    # Run async main
    exit_code = asyncio.run(
        async_main(
            task=task or "",
            repo=repo,
            config_path=config,
            output=output,
            max_rounds=max_rounds,
            dry_run=dry_run,
            verbose=verbose,
            resume=resume,
            no_interactive=no_interactive,
        )
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

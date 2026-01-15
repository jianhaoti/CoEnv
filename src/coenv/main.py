"""
CoEnv CLI - Collaborative Environment Manager

Main entry point for the coenv command-line tool.
"""

import click
import os
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from .core.lexer import parse, get_keys
from .core.syncer import sync_files
from .core.metadata import MetadataStore
from .core.inference import analyze_value
from .core import telemetry


console = Console()


def find_env_files(project_root: str = ".") -> tuple:
    """
    Find .env and .env.example files.

    Args:
        project_root: Project root directory

    Returns:
        Tuple of (env_path, example_path)
    """
    root = Path(project_root)
    env_path = root / ".env"
    example_path = root / ".env.example"

    return str(env_path), str(example_path)


def display_friday_pulse(metadata: MetadataStore):
    """Display the Friday Pulse summary if applicable."""
    if not metadata.should_show_friday_pulse():
        return

    summary = metadata.get_weekly_summary()

    if summary['syncs'] == 0 and summary['saves'] == 0 and summary['doctors'] == 0:
        return  # No activity to show

    panel_content = f"""[bold]Week of {summary['week_start']}[/bold]

Syncs: {summary['syncs']}
Saves: {summary['saves']}
Doctor runs: {summary['doctors']}
Total keys affected: {summary['total_keys_affected']}
Active users: {summary['user_count']} ({', '.join(summary['active_users'])})
"""

    console.print()
    console.print(Panel(
        panel_content,
        title="[bold cyan]Friday Pulse[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED
    ))
    console.print()

    metadata.mark_pulse_shown()


@click.group(invoke_without_command=True)
@click.option('--init', is_flag=True, help='Initialize CoEnv in this project')
@click.option('--watch', is_flag=True, help='Start background file watcher')
@click.pass_context
def cli(ctx, init, watch):
    """
    CoEnv - Intelligent .env to .env.example synchronization
    """
    if ctx.invoked_subcommand is None:
        if init:
            init_project()
        elif watch:
            start_watch()
        else:
            console.print("[yellow]Use --help to see available commands[/yellow]")


@cli.command()
@click.option('--project-root', default=".", help='Project root directory')
def status(project_root):
    """
    Show environment variable status table.

    Displays: Key, Repo Status, Health (Empty check), and Owner.
    """
    metadata = MetadataStore(project_root)
    display_friday_pulse(metadata)

    env_path, example_path = find_env_files(project_root)

    if not Path(env_path).exists():
        console.print("[red]Error: .env file not found[/red]")
        sys.exit(1)

    # Parse .env
    with open(env_path, 'r') as f:
        env_content = f.read()

    env_keys = get_keys(parse(env_content))

    # Parse .env.example if it exists
    example_keys = {}
    if Path(example_path).exists():
        with open(example_path, 'r') as f:
            example_content = f.read()
        example_keys = get_keys(parse(example_content))

    # Create status table
    table = Table(title="Environment Variable Status", box=box.ROUNDED)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Repo Status", style="magenta")
    table.add_column("Health", style="green")
    table.add_column("Owner", style="yellow")

    for key in sorted(env_keys.keys()):
        value = env_keys[key]

        # Determine repo status
        if key in example_keys:
            repo_status = "✓ Synced"
        else:
            repo_status = "✗ Missing"

        # Check health (empty or not)
        if not value or value.strip() == "":
            health = "⚠ Empty"
        else:
            health = "✓ Set"

        # Get owner
        key_meta = metadata.get_key_metadata(key)
        owner = key_meta.owner if key_meta else "unknown"

        table.add_row(key, repo_status, health, owner)

    console.print(table)

    # Track telemetry
    missing_count = sum(1 for k in env_keys if k not in example_keys)
    telemetry.track_status(len(env_keys), missing_count, project_root)


@cli.command()
@click.option('--project-root', default=".", help='Project root directory')
def sync(project_root):
    """
    Sync .env to .env.example.

    Mirrors environment variables from .env to .env.example with
    intelligent placeholders for secrets.
    """
    metadata = MetadataStore(project_root)
    display_friday_pulse(metadata)

    env_path, example_path = find_env_files(project_root)

    if not Path(env_path).exists():
        console.print("[red]Error: .env file not found[/red]")
        sys.exit(1)

    console.print("[cyan]Syncing .env to .env.example...[/cyan]")

    # Perform sync
    updated_content = sync_files(env_path, example_path)

    # Write updated .env.example
    with open(example_path, 'w') as f:
        f.write(updated_content)

    # Update metadata
    with open(env_path, 'r') as f:
        env_content = f.read()

    env_keys = get_keys(parse(env_content))

    for key in env_keys:
        metadata.track_key(key)

    metadata.log_activity("sync", len(env_keys))

    console.print(f"[green]✓ Synced {len(env_keys)} keys to .env.example[/green]")

    # Track telemetry
    telemetry.track_sync(len(env_keys), project_root)


@cli.command()
@click.option('--project-root', default=".", help='Project root directory')
def doctor(project_root):
    """
    Add missing keys from .env.example to .env.

    Safely appends any keys that exist in .env.example but not in .env,
    prompting for values.
    """
    metadata = MetadataStore(project_root)
    display_friday_pulse(metadata)

    env_path, example_path = find_env_files(project_root)

    if not Path(example_path).exists():
        console.print("[red]Error: .env.example file not found[/red]")
        sys.exit(1)

    # Parse both files
    if Path(env_path).exists():
        with open(env_path, 'r') as f:
            env_content = f.read()
        env_keys = get_keys(parse(env_content))
    else:
        env_content = ""
        env_keys = {}

    with open(example_path, 'r') as f:
        example_content = f.read()

    example_keys = get_keys(parse(example_content))

    # Find missing keys
    missing_keys = set(example_keys.keys()) - set(env_keys.keys())

    if not missing_keys:
        console.print("[green]✓ No missing keys - your .env is up to date![/green]")
        return

    console.print(f"[yellow]Found {len(missing_keys)} missing keys in .env[/yellow]")

    # Append missing keys to .env
    with open(env_path, 'a') as f:
        if env_content and not env_content.endswith('\n'):
            f.write('\n')

        f.write('\n# Added by coenv doctor\n')

        for key in sorted(missing_keys):
            placeholder_value = example_keys[key]
            f.write(f"{key}={placeholder_value}\n")
            console.print(f"  [cyan]+ {key}[/cyan]")

    metadata.log_activity("doctor", len(missing_keys))

    console.print(f"\n[green]✓ Added {len(missing_keys)} keys to .env[/green]")
    console.print("[yellow]⚠ Please update the placeholder values with actual values[/yellow]")

    # Track telemetry
    telemetry.track_doctor(len(missing_keys), project_root)


def init_project():
    """Initialize CoEnv in the current project."""
    console.print("[cyan]Initializing CoEnv...[/cyan]")

    # Create .coenv directory
    coenv_dir = Path(".coenv")
    coenv_dir.mkdir(exist_ok=True)

    console.print("[green]✓ Created .coenv directory[/green]")

    # Create git hooks
    git_dir = Path(".git")
    if git_dir.exists():
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)

        # Pre-commit hook
        pre_commit = hooks_dir / "pre-commit"
        pre_commit_content = """#!/bin/sh
# CoEnv pre-commit hook
coenv sync
git add .env.example
"""
        with open(pre_commit, 'w') as f:
            f.write(pre_commit_content)
        pre_commit.chmod(0o755)

        # Post-merge hook
        post_merge = hooks_dir / "post-merge"
        post_merge_content = """#!/bin/sh
# CoEnv post-merge hook
coenv doctor
"""
        with open(post_merge, 'w') as f:
            f.write(post_merge_content)
        post_merge.chmod(0o755)

        console.print("[green]✓ Installed git hooks (pre-commit, post-merge)[/green]")
    else:
        console.print("[yellow]⚠ Not a git repository - skipping git hooks[/yellow]")

    # Create .gitignore entry
    gitignore = Path(".gitignore")
    if gitignore.exists():
        with open(gitignore, 'r') as f:
            content = f.read()

        if '.env' not in content:
            with open(gitignore, 'a') as f:
                f.write('\n# Environment variables\n.env\n')
            console.print("[green]✓ Added .env to .gitignore[/green]")
    else:
        with open(gitignore, 'w') as f:
            f.write('# Environment variables\n.env\n')
        console.print("[green]✓ Created .gitignore with .env[/green]")

    console.print("\n[bold green]✓ CoEnv initialized successfully![/bold green]")
    console.print("\nNext steps:")
    console.print("  1. Run [cyan]coenv sync[/cyan] to create .env.example")
    console.print("  2. Run [cyan]coenv status[/cyan] to check your environment")


def start_watch():
    """Start background file watcher."""
    console.print("[cyan]Starting CoEnv watcher...[/cyan]")
    console.print("[yellow]⚠ Watch mode not yet implemented[/yellow]")
    console.print("For now, use git hooks or run 'coenv sync' manually")


@cli.command()
def mcp():
    """Start MCP (Model Context Protocol) server."""
    from .mcp_server import run_server
    run_server()


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()

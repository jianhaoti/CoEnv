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
from .core.syncer import (
    sync_files, sync_aggregated, add_tombstone, remove_tombstone,
    get_tombstoned_keys, find_fuzzy_tombstone_matches
)
from .core.discovery import discover_env_files, aggregate_env_files, get_example_path
from .core.metadata import MetadataStore
from .core.inference import analyze_value
from .core import telemetry


console = Console()


def find_env_files(project_root: str = ".") -> tuple:
    """
    Find .env and .env.example files (legacy single-file mode).

    Args:
        project_root: Project root directory

    Returns:
        Tuple of (env_path, example_path)
    """
    root = Path(project_root)
    env_path = root / ".env"
    example_path = root / ".env.example"

    return str(env_path), str(example_path)


def discover_and_aggregate(project_root: str = "."):
    """
    Discover all .env* files and aggregate their keys.

    Args:
        project_root: Project root directory

    Returns:
        Tuple of (aggregated_keys dict, example_path, list of discovered file names)
    """
    env_files = discover_env_files(project_root)
    example_path = get_example_path(project_root)

    if not env_files:
        return {}, str(example_path), []

    aggregated_keys = aggregate_env_files(env_files, project_root)
    discovered_files = [f.name for f in env_files]

    return aggregated_keys, str(example_path), discovered_files


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

    Displays: Key, Source, Repo Status, Health (Empty check), and Owner.
    """
    metadata = MetadataStore(project_root)
    display_friday_pulse(metadata)

    # Discover and aggregate all .env* files
    aggregated_keys, example_path, discovered_files = discover_and_aggregate(project_root)

    if not discovered_files:
        console.print("[red]Error: No .env files found[/red]")
        sys.exit(1)

    # Show discovered files
    console.print(f"[cyan]Discovered files:[/cyan] {', '.join(discovered_files)}")
    console.print()

    # Parse .env.example if it exists
    example_keys = {}
    tombstoned = set()
    if Path(example_path).exists():
        with open(example_path, 'r') as f:
            example_content = f.read()
        example_keys = get_keys(parse(example_content))
        tombstoned = get_tombstoned_keys(parse(example_content))

    # Create status table
    table = Table(title="Environment Variable Status", box=box.ROUNDED)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Source", style="blue")
    table.add_column("Repo Status", style="magenta")
    table.add_column("Health", style="green")
    table.add_column("Owner", style="yellow")

    for key in sorted(aggregated_keys.keys()):
        agg_key = aggregated_keys[key]
        value = agg_key.value
        source = agg_key.source

        # Determine repo status
        if key in tombstoned:
            repo_status = "⛔ Deprecated"
        elif key in example_keys:
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

        table.add_row(key, source, repo_status, health, owner)

    console.print(table)

    # Show deprecated keys section if any
    if tombstoned:
        console.print()
        console.print(f"[yellow]Deprecated keys ({len(tombstoned)}):[/yellow]")
        for key in sorted(tombstoned):
            in_local = "[dim](in your .env)[/dim]" if key in aggregated_keys else ""
            console.print(f"  [dim]• {key}[/dim] {in_local}")
        console.print("[dim]Run 'coenv undeprecate KEY' to allow resurrection.[/dim]")

    # Track telemetry
    missing_count = sum(1 for k in aggregated_keys if k not in example_keys and k not in tombstoned)
    telemetry.track_status(len(aggregated_keys), missing_count, project_root)


@cli.command()
@click.option('--project-root', default=".", help='Project root directory')
def sync(project_root):
    """
    Sync all .env* files to .env.example.

    Discovers all .env* files, aggregates keys with priority-based merging,
    and syncs to .env.example with intelligent placeholders for secrets.

    Priority: .env.local > .env.[mode] > .env
    """
    metadata = MetadataStore(project_root)
    display_friday_pulse(metadata)

    # Discover and aggregate all .env* files
    aggregated_keys, example_path, discovered_files = discover_and_aggregate(project_root)

    if not discovered_files:
        console.print("[red]Error: No .env files found[/red]")
        sys.exit(1)

    console.print(f"[cyan]Discovered files:[/cyan] {', '.join(discovered_files)}")
    console.print("[cyan]Syncing to .env.example...[/cyan]")

    # Check for tombstoned keys before sync
    tombstoned = set()
    example_keys_set = set()
    if Path(example_path).exists():
        with open(example_path, 'r') as f:
            example_content = f.read()
        example_tokens = parse(example_content)
        tombstoned = get_tombstoned_keys(example_tokens)
        example_keys_set = set(get_keys(example_tokens).keys())

        # Exact match blocked keys
        blocked_keys = set(aggregated_keys.keys()) & tombstoned
        if blocked_keys:
            console.print(f"\n[yellow]⚠ {len(blocked_keys)} key(s) blocked by tombstones:[/yellow]")
            for key in sorted(blocked_keys):
                console.print(f"  [dim]• {key}[/dim]")
            console.print("[dim]Run 'coenv undeprecate KEY' to allow resurrection.[/dim]\n")

        # Check for fuzzy matches against tombstones for NEW keys
        new_keys = set(aggregated_keys.keys()) - example_keys_set - tombstoned
        fuzzy_matches = find_fuzzy_tombstone_matches(new_keys, tombstoned)

        if fuzzy_matches:
            console.print(f"\n[yellow]⚠ Potential renamed deprecated keys detected:[/yellow]")
            for new_key, tombstone_key in fuzzy_matches.items():
                console.print(f"  [cyan]{new_key}[/cyan] looks similar to deprecated [dim]{tombstone_key}[/dim]")

            # Ask user to confirm
            console.print()
            if click.confirm("Are any of these renamed versions of deprecated keys? (Block them from syncing)", default=False):
                # Let user select which ones to block
                for new_key, tombstone_key in fuzzy_matches.items():
                    if click.confirm(f"  Block '{new_key}' (similar to '{tombstone_key}')?", default=True):
                        tombstoned.add(new_key)  # Treat as tombstoned for this sync
                        console.print(f"    [dim]→ Blocking {new_key}[/dim]")
            console.print()

    # Perform aggregated sync (with any user-blocked keys added to tombstoned set)
    # We need to filter aggregated_keys to exclude user-blocked keys
    filtered_keys = {k: v for k, v in aggregated_keys.items() if k not in tombstoned}
    updated_content, syncer = sync_aggregated(filtered_keys, example_path)

    # Write updated .env.example
    with open(example_path, 'w') as f:
        f.write(updated_content)

    # Update metadata with source tracking (only for non-tombstoned keys)
    if Path(example_path).exists():
        final_tombstoned = get_tombstoned_keys(parse(updated_content))
    else:
        final_tombstoned = set()

    synced_count = 0
    for key, agg_key in aggregated_keys.items():
        if key not in final_tombstoned:
            metadata.track_key(key, source=agg_key.source)
            synced_count += 1

    metadata.log_activity("sync", synced_count)

    console.print(f"[green]✓ Synced {synced_count} keys to .env.example[/green]")

    # Track telemetry
    telemetry.track_sync(synced_count, project_root)


@cli.command()
@click.option('--project-root', default=".", help='Project root directory')
def doctor(project_root):
    """
    Add missing keys from .env.example to .env files.

    Compares .env.example against all discovered .env* files and appends
    any missing keys to the base .env file.
    """
    metadata = MetadataStore(project_root)
    display_friday_pulse(metadata)

    # Discover and aggregate all .env* files
    aggregated_keys, example_path, discovered_files = discover_and_aggregate(project_root)

    if not Path(example_path).exists():
        console.print("[red]Error: .env.example file not found[/red]")
        sys.exit(1)

    # Get the base .env file path for appending missing keys
    env_path = Path(project_root) / ".env"

    # Read existing .env content if it exists
    if env_path.exists():
        with open(env_path, 'r') as f:
            env_content = f.read()
    else:
        env_content = ""

    # Parse .env.example
    with open(example_path, 'r') as f:
        example_content = f.read()

    example_tokens = parse(example_content)
    example_keys = get_keys(example_tokens)
    tombstoned = get_tombstoned_keys(example_tokens)

    # Find missing keys (in .env.example but not in any discovered .env* file)
    missing_keys = set(example_keys.keys()) - set(aggregated_keys.keys())

    # Find deprecated keys that are still in local .env files
    deprecated_in_local = set(aggregated_keys.keys()) & tombstoned

    if discovered_files:
        console.print(f"[cyan]Checked files:[/cyan] {', '.join(discovered_files)}")

    # Warn about deprecated keys in local files
    if deprecated_in_local:
        console.print(f"\n[yellow]⚠ {len(deprecated_in_local)} deprecated key(s) in your local .env files:[/yellow]")
        for key in sorted(deprecated_in_local):
            source = aggregated_keys[key].source
            console.print(f"  [dim]• {key}[/dim] [dim](in {source})[/dim]")
        console.print("[dim]Consider removing these keys as they are no longer used.[/dim]")

    if not missing_keys:
        if not deprecated_in_local:
            console.print("[green]✓ No missing keys - your environment is up to date![/green]")
        return

    console.print(f"\n[yellow]Found {len(missing_keys)} missing keys[/yellow]")

    # Append missing keys to base .env file
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


@cli.command()
@click.argument('key')
@click.option('--project-root', default=".", help='Project root directory')
def deprecate(key, project_root):
    """
    Deprecate a key (add tombstone).

    Marks a key as deprecated so it won't be resurrected even if teammates
    still have it in their .env files. Use this for intentional removals.
    """
    example_path = get_example_path(project_root)

    if not example_path.exists():
        console.print("[red]Error: .env.example file not found[/red]")
        console.print("Run [cyan]coenv sync[/cyan] first to create it.")
        sys.exit(1)

    # Read current content
    with open(example_path, 'r') as f:
        content = f.read()

    # Check if already tombstoned
    tokens = parse(content)
    tombstoned = get_tombstoned_keys(tokens)
    if key in tombstoned:
        console.print(f"[yellow]Key '{key}' is already deprecated[/yellow]")
        return

    # Check if key exists in .env.example or local .env files
    example_keys = get_keys(tokens)
    aggregated_keys, _, discovered_files = discover_and_aggregate(project_root)

    key_exists_in_example = key in example_keys
    key_exists_in_local = key in aggregated_keys

    if not key_exists_in_example and not key_exists_in_local:
        console.print(f"[red]Error: Key '{key}' does not exist[/red]")
        console.print("[dim]Cannot deprecate a key that isn't in .env.example or any .env file.[/dim]")
        sys.exit(1)

    # Add tombstone
    updated_content = add_tombstone(content, key)

    with open(example_path, 'w') as f:
        f.write(updated_content)

    console.print(f"[green]✓ Deprecated '{key}'[/green]")
    console.print("[dim]This key will be blocked from resurrection during sync.[/dim]")


@cli.command()
@click.argument('key')
@click.option('--project-root', default=".", help='Project root directory')
def undeprecate(key, project_root):
    """
    Un-deprecate a key (remove tombstone).

    Removes the tombstone for a key, allowing it to be resurrected
    by teammates who have it in their .env files.
    """
    example_path = get_example_path(project_root)

    if not example_path.exists():
        console.print("[red]Error: .env.example file not found[/red]")
        sys.exit(1)

    # Read current content
    with open(example_path, 'r') as f:
        content = f.read()

    # Check if tombstoned
    tokens = parse(content)
    tombstoned = get_tombstoned_keys(tokens)
    if key not in tombstoned:
        console.print(f"[yellow]Key '{key}' is not deprecated[/yellow]")
        return

    # Remove tombstone
    updated_content = remove_tombstone(content, key)

    with open(example_path, 'w') as f:
        f.write(updated_content)

    console.print(f"[green]✓ Un-deprecated '{key}'[/green]")
    console.print("[dim]This key can now be resurrected during sync.[/dim]")


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

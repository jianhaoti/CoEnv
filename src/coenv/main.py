"""
CoEnv CLI - Collaborative Environment Manager

Main entry point for the coenv command-line tool.
"""

import click
import sys
import subprocess
import re
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from .core.lexer import parse, get_keys, write, Token, TokenType
from .core.excludes import parse_exclude_files, EXCLUDE_FILE_PREFIX
from .core.syncer import (
    sync_aggregated, add_tombstone, remove_tombstone,
    get_tombstoned_keys, find_fuzzy_tombstone_matches, DEPRECATED_MARKER
)
from .core.discovery import discover_env_files, aggregate_env_files, get_example_path
from .core.metadata import MetadataStore
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


def discover_and_aggregate(project_root: str = ".", exclude_files: set[str] | None = None):
    """
    Discover all .env* files and aggregate their keys.

    Args:
        project_root: Project root directory
        exclude_files: Optional set of filenames to skip

    Returns:
        Tuple of (aggregated_keys dict, example_path, list of discovered file names)
    """
    env_files = discover_env_files(project_root, exclude_files=exclude_files)
    example_path = get_example_path(project_root)

    if not env_files:
        return {}, str(example_path), []

    aggregated_keys = aggregate_env_files(env_files, project_root)
    root = Path(project_root)
    discovered_files = []
    for path in env_files:
        try:
            discovered_files.append(str(path.relative_to(root)))
        except ValueError:
            discovered_files.append(path.name)

    return aggregated_keys, str(example_path), discovered_files


def display_friday_pulse(metadata: MetadataStore):
    """Display the Friday Pulse summary if applicable."""
    if not metadata.should_show_friday_pulse():
        return

    summary = metadata.get_weekly_summary()

    if summary['syncs'] == 0 and summary['saves'] == 0:
        return  # No activity to show

    panel_content = f"""[bold]Week of {summary['week_start']}[/bold]

Syncs: {summary['syncs']}
Saves: {summary['saves']}
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


def _git_show_file(project_root: str, ref: str, path: str) -> str | None:
    """Read a file from a git ref; return None if not found."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    return result.stdout


def _git_ref_exists(project_root: str, ref: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _git_blame_author(project_root: str, ref: str | None, path: str, line_no: int) -> str:
    """Return the author for a specific line using git blame."""
    try:
        cmd = ["git", "blame", "-L", f"{line_no},{line_no}", "--line-porcelain"]
        if ref:
            cmd.extend([ref, "--", path])
        else:
            cmd.extend(["--", path])

        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"

    if result.returncode != 0:
        return "unknown"

    for line in result.stdout.splitlines():
        if line.startswith("author "):
            return line[len("author "):].strip() or "unknown"

    return "unknown"


def _line_map_keys(content: str) -> dict[str, int]:
    """Map env keys to line numbers (1-based)."""
    mapping: dict[str, int] = {}
    key_re = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
    for idx, line in enumerate(content.splitlines(), start=1):
        match = key_re.match(line)
        if match:
            mapping[match.group(1)] = idx
    return mapping


def _line_map_tombstones(content: str) -> dict[str, int]:
    """Map tombstoned keys to line numbers (1-based)."""
    mapping: dict[str, int] = {}
    tombstone_re = re.compile(r"^\s*#\s*\[TOMBSTONE\]\s+([A-Za-z_][A-Za-z0-9_]*)\s+-\s+Deprecated on:")
    for idx, line in enumerate(content.splitlines(), start=1):
        match = tombstone_re.match(line)
        if match:
            mapping[match.group(1)] = idx
    return mapping


def _has_conflict_markers(content: str) -> bool:
    """Detect merge conflict markers in a file."""
    for line in content.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("<<<<<<<") or stripped.startswith("=======") or stripped.startswith(">>>>>>>"):
            return True
    return False


def _read_example_content(project_root: str) -> str:
    """Read .env.example content if it exists."""
    example_path = get_example_path(project_root)
    if not example_path.exists():
        return ""

    try:
        return example_path.read_text()
    except OSError:
        return ""


def _get_excluded_files(project_root: str) -> set[str]:
    """Get excluded file list from .env.example."""
    content = _read_example_content(project_root)
    if not content:
        return set()

    return parse_exclude_files(content)


def report_example_changes(project_root: str = ".") -> None:
    """
    Report .env.example changes from the last merge/rewrite.
    """
    base_ref = "ORIG_HEAD" if _git_ref_exists(project_root, "ORIG_HEAD") else "HEAD@{1}"
    if not _git_ref_exists(project_root, base_ref):
        return

    base_content = _git_show_file(project_root, base_ref, ".env.example")
    head_content = _git_show_file(project_root, "HEAD", ".env.example")

    if base_content is None or head_content is None:
        return

    base_tokens = parse(base_content)
    head_tokens = parse(head_content)
    base_keys = set(get_keys(base_tokens).keys())
    head_keys = set(get_keys(head_tokens).keys())
    base_tombstones = get_tombstoned_keys(base_tokens)
    head_tombstones = get_tombstoned_keys(head_tokens)

    added_keys = head_keys - base_keys
    removed_keys = base_keys - head_keys
    new_tombstones = head_tombstones - base_tombstones
    removed_keys = removed_keys - new_tombstones

    if not added_keys and not removed_keys and not new_tombstones:
        console.print("[dim]No .env.example changes detected in this merge.[/dim]")
        return

    key_line_map = _line_map_keys(head_content)
    tombstone_line_map = _line_map_tombstones(head_content)

    console.print("\n[bold]CoEnv changes from merge[/bold]")

    if added_keys:
        console.print("[green]Added keys:[/green]")
        for key in sorted(added_keys):
            line_no = key_line_map.get(key)
            owner = _git_blame_author(project_root, None, ".env.example", line_no) if line_no else "unknown"
            console.print(f"  [green]+ {key}[/green] [dim](owner: {owner})[/dim]")

    if new_tombstones:
        console.print("[yellow]Deprecated keys:[/yellow]")
        for key in sorted(new_tombstones):
            line_no = tombstone_line_map.get(key)
            owner = _git_blame_author(project_root, None, ".env.example", line_no) if line_no else "unknown"
            console.print(f"  [yellow]~ {key}[/yellow] [dim](owner: {owner})[/dim]")

    if removed_keys:
        console.print("[red]Removed keys:[/red]")
        for key in sorted(removed_keys):
            console.print(f"  [red]- {key}[/red]")


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

    example_content = _read_example_content(project_root)
    if example_content and _has_conflict_markers(example_content):
        console.print("[red]Error: .env.example contains merge conflict markers[/red]")
        console.print("[dim]Resolve conflicts before running commit-hook.[/dim]")
        sys.exit(1)

    excluded_files = parse_exclude_files(example_content) if example_content else set()

    local_env = Path(project_root) / ".env.local"
    if local_env.exists() and ".env.local" not in excluded_files:
        console.print("[red]Error: .env.local is present but not excluded[/red]")
        console.print("[dim]Run 'coenv exclude-file .env.local' to skip it.[/dim]")
        sys.exit(1)

    # Discover and aggregate all .env* files
    aggregated_keys, example_path, discovered_files = discover_and_aggregate(
        project_root,
        exclude_files=excluded_files
    )

    if not discovered_files:
        console.print("[yellow]No .env files found - skipping .env.example update[/yellow]")
        return

    # Show discovered files
    console.print(f"[cyan]Discovered files:[/cyan] {', '.join(discovered_files)}")
    if excluded_files:
        console.print(f"[dim]Excluded files:[/dim] {', '.join(sorted(excluded_files))}")
    console.print()

    # Parse .env.example if it exists
    example_keys = {}
    tombstoned = set()
    example_line_map = {}
    if Path(example_path).exists():
        with open(example_path, 'r') as f:
            example_content = f.read()
        example_keys = get_keys(parse(example_content))
        tombstoned = get_tombstoned_keys(parse(example_content))
        example_line_map = _line_map_keys(example_content)

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
        line_no = example_line_map.get(key)
        if line_no:
            owner = _git_blame_author(project_root, None, ".env.example", line_no)
        else:
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


@cli.command(name="commit-hook", hidden=True)
@click.option('--project-root', default=".", help='Project root directory')
def commit_hook(project_root):
    """
    Internal: sync .env* files to .env.example during git hooks.

    Discovers all .env* files, aggregates keys with priority-based merging,
    and syncs to .env.example with intelligent placeholders for secrets.

    Priority: .env.local > .env.[mode] > .env
    """
    metadata = MetadataStore(project_root)
    display_friday_pulse(metadata)

    example_content = _read_example_content(project_root)
    if example_content and _has_conflict_markers(example_content):
        console.print("[red]Error: .env.example contains merge conflict markers[/red]")
        console.print("[dim]Resolve conflicts before running commit-hook.[/dim]")
        sys.exit(1)

    excluded_files = parse_exclude_files(example_content) if example_content else set()

    local_env = Path(project_root) / ".env.local"
    if local_env.exists() and ".env.local" not in excluded_files:
        console.print("[red]Error: .env.local is present but not excluded[/red]")
        console.print("[dim]Run 'coenv exclude-file .env.local' to skip it.[/dim]")
        sys.exit(1)

    # Discover and aggregate all .env* files
    aggregated_keys, example_path, discovered_files = discover_and_aggregate(
        project_root,
        exclude_files=excluded_files
    )

    if not discovered_files:
        console.print("[yellow]No .env files found - skipping .env.example update[/yellow]")
        return

    console.print(f"[cyan]Discovered files:[/cyan] {', '.join(discovered_files)}")
    if excluded_files:
        console.print(f"[dim]Excluded files:[/dim] {', '.join(sorted(excluded_files))}")
    console.print("[cyan]Generating .env.example...[/cyan]")

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
            console.print("[dim]Review these to avoid resurrecting deprecated keys.[/dim]\n")

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

    console.print(f"[green]✓ Updated {synced_count} keys in .env.example[/green]")

    # Track telemetry
    telemetry.track_sync(synced_count, project_root)


@cli.command(name="merge-hook", hidden=True)
@click.option('--project-root', default=".", help='Project root directory')
@click.option('--no-report', is_flag=True, help='Skip reporting merge changes')
def merge_hook(project_root, no_report):
    """
    Internal: report changes after merge/rewrite, then regenerate .env.example.
    """
    example_content = _read_example_content(project_root)
    if example_content and _has_conflict_markers(example_content):
        console.print("[red]Error: .env.example contains merge conflict markers[/red]")
        console.print("[dim]Resolve conflicts before running merge-hook.[/dim]")
        sys.exit(1)

    if not no_report:
        report_example_changes(project_root)
    commit_hook(project_root)


@cli.command(name="exclude-file")
@click.argument('filename')
@click.option('--project-root', default=".", help='Project root directory')
def exclude_file(filename, project_root):
    """
    Exclude an env file from .env.example generation.

    Writes an exclude marker into .env.example.
    """
    example_path = get_example_path(project_root)
    content = ""
    if example_path.exists():
        content = example_path.read_text()
        if _has_conflict_markers(content):
            console.print("[red]Error: .env.example contains merge conflict markers[/red]")
            console.print("[dim]Resolve conflicts before updating excludes.[/dim]")
            sys.exit(1)

    excluded = parse_exclude_files(content)
    if filename in excluded:
        console.print(f"[yellow]{filename} is already excluded[/yellow]")
        return

    tokens = parse(content) if content else []
    marker_line = f"# {EXCLUDE_FILE_PREFIX} {filename}\n"
    marker = Token(TokenType.COMMENT, raw=marker_line)

    insert_idx = len(tokens)
    for i, token in enumerate(tokens):
        if token.type == TokenType.KEY_VALUE:
            insert_idx = i
            break
        if token.type == TokenType.COMMENT and DEPRECATED_MARKER in token.raw:
            insert_idx = i
            break

    tokens.insert(insert_idx, marker)

    # Ensure a blank line after the marker if keys follow immediately.
    if insert_idx + 1 < len(tokens) and tokens[insert_idx + 1].type == TokenType.KEY_VALUE:
        tokens.insert(insert_idx + 1, Token(TokenType.BLANK_LINE, raw="\n"))

    example_path.write_text(write(tokens))
    console.print(f"[green]✓ Excluded {filename} from .env.example generation[/green]")


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
        console.print("[dim]Create .env.example via a commit (pre-commit hook) before deprecating.[/dim]")
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
    excluded_files = _get_excluded_files(project_root)
    aggregated_keys, _, discovered_files = discover_and_aggregate(
        project_root,
        exclude_files=excluded_files
    )

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
    console.print("[dim]This key will be blocked from resurrection during commit-hook generation.[/dim]")


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
    console.print("[dim]This key can now be resurrected during commit-hook generation.[/dim]")


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
set -e
command -v coenv >/dev/null 2>&1 || { echo "coenv not found in PATH"; exit 1; }
# CoEnv pre-commit hook
coenv commit-hook
git add .env.example
"""
        with open(pre_commit, 'w') as f:
            f.write(pre_commit_content)
        pre_commit.chmod(0o755)

        # Post-merge hook
        post_merge = hooks_dir / "post-merge"
        post_merge_content = """#!/bin/sh
set -e
command -v coenv >/dev/null 2>&1 || { echo "coenv not found in PATH"; exit 1; }
# CoEnv post-merge hook
coenv merge-hook
"""
        with open(post_merge, 'w') as f:
            f.write(post_merge_content)
        post_merge.chmod(0o755)

        # Post-rewrite hook (runs after rebase/amend)
        post_rewrite = hooks_dir / "post-rewrite"
        post_rewrite_content = """#!/bin/sh
set -e
command -v coenv >/dev/null 2>&1 || { echo "coenv not found in PATH"; exit 1; }
# CoEnv post-rewrite hook
coenv merge-hook
"""
        with open(post_rewrite, 'w') as f:
            f.write(post_rewrite_content)
        post_rewrite.chmod(0o755)

        console.print("[green]✓ Installed git hooks (pre-commit, post-merge, post-rewrite)[/green]")
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
    console.print("  1. Make a commit (pre-commit hook generates .env.example)")
    console.print("  2. Run [cyan]coenv status[/cyan] to check your environment")


def start_watch():
    """Start background file watcher."""
    console.print("[cyan]Starting CoEnv watcher...[/cyan]")
    console.print("[yellow]⚠ Watch mode not yet implemented[/yellow]")
    console.print("For now, rely on the git pre-commit hook to update .env.example")


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

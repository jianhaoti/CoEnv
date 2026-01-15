"""
Multi-file discovery and aggregation for .env files.

Discovers all .env* files in a project and aggregates their keys
with priority-based merging and source tracking.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .lexer import parse, get_keys


@dataclass
class AggregatedKey:
    """Represents a key aggregated from multiple .env files."""
    key: str
    value: str
    source: str  # Primary source file (highest priority)
    all_sources: list[str] = field(default_factory=list)  # All files containing this key


def get_file_priority(filename: str) -> int:
    """
    Get priority for an env file.

    Priority order (highest first):
    - .env.local = 100 (always highest, local overrides)
    - .env.[mode] = 50 (e.g., .env.development, .env.production)
    - .env = 0 (base file, lowest priority)

    Args:
        filename: Name of the file (e.g., ".env.local")

    Returns:
        Priority value (higher = more important)
    """
    if filename == ".env.local":
        return 100
    elif filename == ".env":
        return 0
    elif filename.startswith(".env."):
        # Any .env.[mode] file gets middle priority
        return 50
    return 0


def discover_env_files(project_root: str = ".") -> list[Path]:
    """
    Discover all .env* files in project root.

    Excludes:
    - .env.example (the output file)
    - Files inside .coenv/ folder

    Args:
        project_root: Path to project root directory

    Returns:
        List of Path objects sorted by priority (highest first)
    """
    root = Path(project_root)
    env_files = []

    # Find all .env* files in root directory only (not recursive)
    for path in root.iterdir():
        if not path.is_file():
            continue

        name = path.name

        # Must start with .env
        if not name.startswith(".env"):
            continue

        # Exclude .env.example
        if name == ".env.example":
            continue

        # Exclude anything in .coenv/ (shouldn't happen at root level, but be safe)
        if ".coenv" in path.parts:
            continue

        env_files.append(path)

    # Sort by priority (highest first)
    env_files.sort(key=lambda p: get_file_priority(p.name), reverse=True)

    return env_files


def aggregate_env_files(
    files: list[Path],
    project_root: Optional[str] = None
) -> dict[str, AggregatedKey]:
    """
    Aggregate keys from multiple .env files with priority-based merging.

    If a key appears in multiple files:
    - Use value from highest priority file for placeholder inference
    - Track primary source (highest priority file)
    - Track all files containing this key in all_sources

    Args:
        files: List of env file paths, sorted by priority (highest first)
        project_root: Optional project root for relative path display

    Returns:
        Dictionary mapping key names to AggregatedKey objects
    """
    aggregated: dict[str, AggregatedKey] = {}
    root = Path(project_root) if project_root else None

    # Process files in priority order (highest first)
    # First file to define a key "wins" for value/source
    for file_path in files:
        if not file_path.exists():
            continue

        content = file_path.read_text()
        tokens = parse(content)
        keys = get_keys(tokens)

        # Get display name (relative to root or just filename)
        if root:
            try:
                display_name = str(file_path.relative_to(root))
            except ValueError:
                display_name = file_path.name
        else:
            display_name = file_path.name

        for key, value in keys.items():
            if key in aggregated:
                # Key already exists from higher priority file
                # Just add this file to all_sources
                if display_name not in aggregated[key].all_sources:
                    aggregated[key].all_sources.append(display_name)
            else:
                # First occurrence - this file is the primary source
                aggregated[key] = AggregatedKey(
                    key=key,
                    value=value,
                    source=display_name,
                    all_sources=[display_name]
                )

    return aggregated


def get_example_path(project_root: str = ".") -> Path:
    """
    Get the path to .env.example file.

    Args:
        project_root: Path to project root directory

    Returns:
        Path to .env.example
    """
    return Path(project_root) / ".env.example"

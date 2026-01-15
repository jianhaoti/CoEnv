"""
Multi-file discovery and aggregation for .env files.

Discovers all .env* files in a project and aggregates their keys
with priority-based merging and source tracking.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import os

ENV_CACHE_FILE = ".coenv/env_cache.json"
DEFAULT_PRUNE_DIRS = {
    ".git",
    ".coenv",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
}

from .lexer import parse, get_keys


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def _is_excluded(path: Path, root: Path, excluded: set[str]) -> bool:
    if not excluded:
        return False
    if path.name in excluded:
        return True
    try:
        rel_name = str(path.relative_to(root))
    except ValueError:
        return False
    return rel_name in excluded


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


def _load_env_cache(project_root: str) -> list[Path] | None:
    cache_path = Path(project_root) / ENV_CACHE_FILE
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    if data.get("root") != str(Path(project_root).resolve()):
        return None

    files = []
    for rel_path in data.get("files", []):
        path = Path(project_root) / rel_path
        if path.exists():
            files.append(path)
    return files


def _save_env_cache(project_root: str, files: list[Path]) -> None:
    cache_path = Path(project_root) / ENV_CACHE_FILE
    cache_path.parent.mkdir(exist_ok=True)
    data = {
        "root": str(Path(project_root).resolve()),
        "files": [str(path.relative_to(project_root)) for path in files],
    }
    try:
        cache_path.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def discover_env_files(
    project_root: str = ".",
    exclude_files: Optional[set[str]] = None,
    recursive: bool | None = None,
    use_cache: bool | None = None,
) -> list[Path]:
    """
    Discover all .env* files in project root.

    Excludes:
    - .env.example (the output file)
    - Files inside .coenv/ folder

    Args:
        project_root: Path to project root directory
        exclude_files: Optional set of filenames or relative paths to skip
        recursive: If True, scan subdirectories (monorepo support)
        use_cache: If True, use cached paths when available

    Environment:
        COENV_RECURSIVE=0 disables recursive scanning
        COENV_USE_SCAN_CACHE=1 enables cached path usage

    Notes:
        Cached scans are best-effort and may miss newly added env files until refreshed.

    Returns:
        List of Path objects sorted by priority (highest first)
    """
    root = Path(project_root)
    env_files = []
    excluded = exclude_files or set()
    if recursive is None:
        recursive = _env_bool("COENV_RECURSIVE", True)
    if use_cache is None:
        use_cache = _env_bool("COENV_USE_SCAN_CACHE", False)

    if use_cache:
        cached = _load_env_cache(project_root)
        if cached is not None:
            env_files = [path for path in cached if not _is_excluded(path, root, excluded)]
        else:
            use_cache = False

    if not use_cache:
        if recursive:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in DEFAULT_PRUNE_DIRS]

                for filename in filenames:
                    if not filename.startswith(".env"):
                        continue
                    if filename == ".env.example":
                        continue

                    path = Path(dirpath) / filename

                    if ".coenv" in path.parts:
                        continue

                    if _is_excluded(path, root, excluded):
                        continue

                    env_files.append(path)
        else:
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

                # Skip excluded files by name or relative path
                if _is_excluded(path, root, excluded):
                    continue

                env_files.append(path)

        _save_env_cache(project_root, env_files)

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

"""
Exclude markers for .env.example.
"""

from typing import Set


EXCLUDE_FILE_PREFIX = "[EXCLUDE_FILE]"


def parse_exclude_files(content: str) -> Set[str]:
    """
    Parse excluded file markers from .env.example content.

    Expected line format: "# [EXCLUDE_FILE] .env.local"
    """
    excluded: Set[str] = set()

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue

        if EXCLUDE_FILE_PREFIX not in stripped:
            continue

        # Split on the marker and take the remainder as the filename
        _, remainder = stripped.split(EXCLUDE_FILE_PREFIX, 1)
        filename = remainder.strip(" :")
        if filename:
            excluded.add(filename)

    return excluded

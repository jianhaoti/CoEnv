"""
CoEnv core modules.

Includes:
- lexer: Token-based .env file parsing
- inference: Secret and encryption detection
- syncer: Sync logic with fuzzy matching and tombstones
- metadata: Ownership tracking and reporting
- telemetry: Anonymous usage tracking
- excludes: Exclude markers for .env.example
"""

from . import lexer
from . import inference
from . import syncer
from . import metadata
from . import telemetry
from . import excludes

__all__ = [
    "lexer",
    "inference",
    "syncer",
    "metadata",
    "telemetry",
    "excludes",
]

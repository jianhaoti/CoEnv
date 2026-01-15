"""
CoEnv core modules.

Includes:
- lexer: Token-based .env file parsing
- inference: Secret and encryption detection
- syncer: Sync logic with fuzzy matching and graveyard
- metadata: Ownership tracking and reporting
- telemetry: Anonymous usage tracking
"""

from . import lexer
from . import inference
from . import syncer
from . import metadata
from . import telemetry

__all__ = [
    "lexer",
    "inference",
    "syncer",
    "metadata",
    "telemetry",
]

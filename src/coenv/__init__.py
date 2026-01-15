"""
CoEnv - Collaborative Environment Manager

An intelligent, lossless, and ownership-aware bridge between your local .env
and your team's .env.example.
"""

__version__ = "0.1.0"

from .core import lexer, inference, syncer, metadata

__all__ = [
    "lexer",
    "inference",
    "syncer",
    "metadata",
]

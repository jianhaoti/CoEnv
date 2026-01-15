"""
Lossless .env file lexer with byte-perfect round-trip guarantee.

This module implements a token-stream parser for .env files that preserves
all whitespace, comments, and formatting. The constraint is:
    write(parse(file)) == file (byte-identical)
"""

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class TokenType(Enum):
    """Token types for .env file parsing."""
    COMMENT = "comment"
    BLANK_LINE = "blank_line"
    KEY_VALUE = "key_value"
    EXPORT_PREFIX = "export_prefix"


@dataclass
class Token:
    """A single token in the .env file."""
    type: TokenType
    raw: str  # Original text, preserves everything
    key: Optional[str] = None
    value: Optional[str] = None
    has_export: bool = False

    def __repr__(self):
        if self.type == TokenType.KEY_VALUE:
            export = "export " if self.has_export else ""
            return f"Token({self.type.value}, {export}{self.key}={self.value})"
        return f"Token({self.type.value}, {repr(self.raw[:20])}...)"


class Lexer:
    """
    Lossless lexer for .env files.

    Tokenizes .env files into a stream of tokens that can be perfectly
    reconstructed back to the original file.
    """

    def __init__(self, content: str):
        self.content = content
        self.lines = content.splitlines(keepends=True)

    def tokenize(self) -> List[Token]:
        """
        Parse content into tokens.

        Returns:
            List of Token objects representing the file structure.
        """
        tokens = []

        for line in self.lines:
            token = self._parse_line(line)
            tokens.append(token)

        return tokens

    def _parse_line(self, line: str) -> Token:
        """Parse a single line into a token."""
        stripped = line.lstrip()

        # Blank line (empty or only whitespace)
        if not stripped or stripped == '\n':
            return Token(
                type=TokenType.BLANK_LINE,
                raw=line
            )

        # Comment line
        if stripped.startswith('#'):
            return Token(
                type=TokenType.COMMENT,
                raw=line
            )

        # Key-value line (potentially with export prefix)
        if '=' in stripped:
            # Check for export prefix
            has_export = False
            working_line = stripped

            if stripped.startswith('export '):
                has_export = True
                working_line = stripped[7:]  # Remove 'export '

            # Find the first '=' to split key and value
            eq_index = working_line.index('=')
            key = working_line[:eq_index].strip()
            value = working_line[eq_index + 1:]

            # Remove trailing newline from value for storage
            # but keep it in raw
            if value.endswith('\n'):
                value = value[:-1]

            # Handle quoted values
            value_stripped = value.strip()
            if value_stripped:
                # Check if value is quoted
                if ((value_stripped.startswith('"') and value_stripped.endswith('"')) or
                    (value_stripped.startswith("'") and value_stripped.endswith("'"))):
                    # Store without quotes
                    value = value_stripped[1:-1]
                else:
                    # Store as-is (trimmed)
                    value = value_stripped
            else:
                value = ""

            return Token(
                type=TokenType.KEY_VALUE,
                raw=line,
                key=key,
                value=value,
                has_export=has_export
            )

        # Default: treat as comment/unknown
        return Token(
            type=TokenType.COMMENT,
            raw=line
        )


def parse(content: str) -> List[Token]:
    """
    Parse .env file content into tokens.

    Args:
        content: String content of .env file

    Returns:
        List of Token objects
    """
    lexer = Lexer(content)
    return lexer.tokenize()


def write(tokens: List[Token]) -> str:
    """
    Reconstruct .env file from tokens.

    Args:
        tokens: List of Token objects

    Returns:
        String content that should be byte-identical to original
    """
    return ''.join(token.raw for token in tokens)


def get_keys(tokens: List[Token]) -> dict:
    """
    Extract all key-value pairs from tokens.

    Args:
        tokens: List of Token objects

    Returns:
        Dictionary of key-value pairs
    """
    return {
        token.key: token.value
        for token in tokens
        if token.type == TokenType.KEY_VALUE and token.key
    }


def update_value(tokens: List[Token], key: str, new_value: str) -> List[Token]:
    """
    Update a value in the token stream.

    Args:
        tokens: List of Token objects
        key: Key to update
        new_value: New value for the key

    Returns:
        Updated list of tokens with modified raw text
    """
    updated = []
    for token in tokens:
        if token.type == TokenType.KEY_VALUE and token.key == key:
            # Reconstruct the line with new value
            export_prefix = "export " if token.has_export else ""
            # Preserve the original line ending
            line_ending = '\n' if token.raw.endswith('\n') else ''

            # Quote the value if it contains spaces or special chars
            if ' ' in new_value or '#' in new_value:
                quoted_value = f'"{new_value}"'
            else:
                quoted_value = new_value

            new_raw = f"{export_prefix}{key}={quoted_value}{line_ending}"

            updated.append(Token(
                type=TokenType.KEY_VALUE,
                raw=new_raw,
                key=key,
                value=new_value,
                has_export=token.has_export
            ))
        else:
            updated.append(token)

    return updated

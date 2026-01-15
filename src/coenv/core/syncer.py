"""
Synchronization logic for .env -> .env.example with fuzzy matching and graveyard.

Key features:
- Fuzzy rename detection (difflib.SequenceMatcher > 0.8)
- Sticky values (never overwrite manual edits in .env.example)
- The Graveyard (deprecated keys with 14-day TTL)
"""

import difflib
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional
from .lexer import Token, TokenType, parse, write, get_keys, update_value
from .inference import generate_placeholder


GRAVEYARD_MARKER = "# === DEPRECATED ==="
GRAVEYARD_TTL_DAYS = 14
FUZZY_MATCH_THRESHOLD = 0.8


def find_fuzzy_match(key: str, candidates: List[str], threshold: float = FUZZY_MATCH_THRESHOLD) -> Optional[str]:
    """
    Find the best fuzzy match for a key among candidates.

    Args:
        key: Key to match
        candidates: List of candidate keys
        threshold: Minimum similarity ratio (default 0.8)

    Returns:
        Best matching key or None if no match above threshold
    """
    if not candidates:
        return None

    best_match = None
    best_ratio = threshold

    for candidate in candidates:
        ratio = difflib.SequenceMatcher(None, key.lower(), candidate.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = candidate

    return best_match


def parse_graveyard_entry(comment_line: str) -> Optional[Tuple[str, datetime]]:
    """
    Parse a graveyard comment to extract key and removal date.

    Expected format: "# KEY_NAME - Removed on: YYYY-MM-DD"

    Args:
        comment_line: Comment line from graveyard section

    Returns:
        Tuple of (key, removal_date) or None if not a graveyard entry
    """
    if not comment_line.strip().startswith('#'):
        return None

    # Remove leading '#' and whitespace
    content = comment_line.strip()[1:].strip()

    if '- Removed on:' not in content:
        return None

    try:
        parts = content.split('- Removed on:')
        key = parts[0].strip()
        date_str = parts[1].strip()
        removal_date = datetime.strptime(date_str, '%Y-%m-%d')
        return (key, removal_date)
    except (ValueError, IndexError):
        return None


def is_graveyard_expired(removal_date: datetime) -> bool:
    """
    Check if a graveyard entry has expired.

    Args:
        removal_date: Date when key was removed

    Returns:
        True if entry is older than GRAVEYARD_TTL_DAYS
    """
    expiry_date = removal_date + timedelta(days=GRAVEYARD_TTL_DAYS)
    return datetime.now() > expiry_date


class Syncer:
    """
    Manages synchronization from .env to .env.example.
    """

    def __init__(self, env_content: str, example_content: str):
        """
        Initialize syncer with file contents.

        Args:
            env_content: Content of .env file
            example_content: Content of .env.example file
        """
        self.env_tokens = parse(env_content)
        self.example_tokens = parse(example_content)

        self.env_keys = get_keys(self.env_tokens)
        self.example_keys = get_keys(self.example_tokens)

    def sync(self, preserve_manual_edits: bool = True) -> str:
        """
        Sync .env to .env.example with fuzzy matching and graveyard logic.

        Args:
            preserve_manual_edits: If True, don't overwrite values in .env.example

        Returns:
            Updated .env.example content
        """
        # Step 1: Clean up expired graveyard entries
        self.example_tokens = self._cleanup_graveyard()

        # Step 2: Update existing keys and detect renames
        updated_keys = set()
        renamed_from_keys = set()  # Track original keys that were renamed
        new_tokens = []

        for token in self.example_tokens:
            if token.type == TokenType.KEY_VALUE and token.key:
                # Check if key still exists in .env
                if token.key in self.env_keys:
                    # Key exists - update placeholder if not manually edited
                    new_value = generate_placeholder(token.key, self.env_keys[token.key])

                    if preserve_manual_edits and not token.value.startswith('<your_'):
                        # Sticky value - keep manual edit
                        new_tokens.append(token)
                    else:
                        # Update to new placeholder
                        updated = Token(
                            type=TokenType.KEY_VALUE,
                            raw=self._reconstruct_line(token.key, new_value, token.has_export),
                            key=token.key,
                            value=new_value,
                            has_export=token.has_export
                        )
                        new_tokens.append(updated)

                    updated_keys.add(token.key)
                else:
                    # Key doesn't exist - check for fuzzy rename
                    remaining_env_keys = [k for k in self.env_keys.keys() if k not in updated_keys]
                    fuzzy_match = find_fuzzy_match(token.key, remaining_env_keys)

                    if fuzzy_match:
                        # Rename detected - update key and value
                        new_value = generate_placeholder(fuzzy_match, self.env_keys[fuzzy_match])
                        renamed = Token(
                            type=TokenType.KEY_VALUE,
                            raw=self._reconstruct_line(fuzzy_match, new_value, token.has_export),
                            key=fuzzy_match,
                            value=new_value,
                            has_export=token.has_export
                        )
                        new_tokens.append(renamed)
                        updated_keys.add(fuzzy_match)
                        renamed_from_keys.add(token.key)  # Track original key
                    else:
                        # Key truly removed - move to graveyard
                        new_tokens.append(token)
            else:
                # Non-key-value token - keep as-is
                new_tokens.append(token)

        # Step 3: Add new keys from .env
        new_keys = set(self.env_keys.keys()) - updated_keys

        if new_keys:
            # Add before graveyard if it exists, otherwise at end
            graveyard_index = self._find_graveyard_index(new_tokens)

            for key in sorted(new_keys):
                value = generate_placeholder(key, self.env_keys[key])
                new_token = Token(
                    type=TokenType.KEY_VALUE,
                    raw=self._reconstruct_line(key, value, False),
                    key=key,
                    value=value,
                    has_export=False
                )

                if graveyard_index is not None:
                    new_tokens.insert(graveyard_index, new_token)
                    graveyard_index += 1
                else:
                    new_tokens.append(new_token)

        # Step 4: Move removed keys to graveyard (excluding renamed keys)
        removed_keys = set(self.example_keys.keys()) - set(self.env_keys.keys()) - updated_keys - renamed_from_keys

        if removed_keys:
            new_tokens = self._add_to_graveyard(new_tokens, removed_keys)

        return write(new_tokens)

    def _cleanup_graveyard(self) -> List[Token]:
        """Remove expired entries from graveyard."""
        new_tokens = []
        in_graveyard = False

        for token in self.example_tokens:
            if token.type == TokenType.COMMENT and GRAVEYARD_MARKER in token.raw:
                in_graveyard = True
                new_tokens.append(token)
                continue

            if in_graveyard and token.type == TokenType.COMMENT:
                entry = parse_graveyard_entry(token.raw)
                if entry:
                    key, removal_date = entry
                    if not is_graveyard_expired(removal_date):
                        # Keep non-expired entry
                        new_tokens.append(token)
                    # Expired entries are simply not added
                else:
                    # Regular comment in graveyard
                    new_tokens.append(token)
            else:
                new_tokens.append(token)

        return new_tokens

    def _add_to_graveyard(self, tokens: List[Token], removed_keys: Set[str]) -> List[Token]:
        """Add removed keys to graveyard section."""
        if not removed_keys:
            return tokens

        # Check if graveyard exists
        graveyard_index = self._find_graveyard_index(tokens)
        today = datetime.now().strftime('%Y-%m-%d')

        if graveyard_index is None:
            # Create graveyard section at end
            if tokens and tokens[-1].type != TokenType.BLANK_LINE:
                tokens.append(Token(TokenType.BLANK_LINE, raw='\n'))

            tokens.append(Token(TokenType.COMMENT, raw=f"{GRAVEYARD_MARKER}\n"))

            for key in sorted(removed_keys):
                comment = f"# {key} - Removed on: {today}\n"
                tokens.append(Token(TokenType.COMMENT, raw=comment))
        else:
            # Add to existing graveyard
            for key in sorted(removed_keys):
                comment = f"# {key} - Removed on: {today}\n"
                tokens.insert(graveyard_index + 1, Token(TokenType.COMMENT, raw=comment))

        return tokens

    def _find_graveyard_index(self, tokens: List[Token]) -> Optional[int]:
        """Find the index of the graveyard marker."""
        for i, token in enumerate(tokens):
            if token.type == TokenType.COMMENT and GRAVEYARD_MARKER in token.raw:
                return i
        return None

    def _reconstruct_line(self, key: str, value: str, has_export: bool) -> str:
        """Reconstruct a key-value line."""
        export_prefix = "export " if has_export else ""

        # Quote value if it contains spaces or special chars
        if ' ' in value or '#' in value:
            quoted_value = f'"{value}"'
        else:
            quoted_value = value

        return f"{export_prefix}{key}={quoted_value}\n"


def sync_files(env_path: str, example_path: str) -> str:
    """
    Sync .env file to .env.example.

    Args:
        env_path: Path to .env file
        example_path: Path to .env.example file

    Returns:
        Updated .env.example content
    """
    with open(env_path, 'r') as f:
        env_content = f.read()

    try:
        with open(example_path, 'r') as f:
            example_content = f.read()
    except FileNotFoundError:
        example_content = ""

    syncer = Syncer(env_content, example_content)
    return syncer.sync()

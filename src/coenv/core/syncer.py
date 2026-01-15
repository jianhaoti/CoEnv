"""
Synchronization logic for .env -> .env.example with fuzzy matching and tombstones.

Key features:
- Fuzzy rename detection (difflib.SequenceMatcher > 0.6)
- Sticky values (never overwrite manual edits in .env.example)
- Tombstones (explicitly deprecated keys that block resurrection)
- Multi-file aggregation with priority-based merging
"""

import difflib
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional, TYPE_CHECKING
from .lexer import Token, TokenType, parse, write, get_keys, update_value
from .inference import generate_placeholder

if TYPE_CHECKING:
    from .discovery import AggregatedKey


DEPRECATED_MARKER = "# === DEPRECATED ==="
TOMBSTONE_PREFIX = "[TOMBSTONE]"
FUZZY_MATCH_THRESHOLD = 0.6


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


def parse_tombstone(comment_line: str) -> Optional[Tuple[str, datetime]]:
    """
    Parse a tombstone comment to extract key and deprecation date.

    Expected format: "# [TOMBSTONE] KEY_NAME - Deprecated on: YYYY-MM-DD"

    Args:
        comment_line: Comment line from deprecated section

    Returns:
        Tuple of (key, deprecation_date) or None if not a tombstone
    """
    if not comment_line.strip().startswith('#'):
        return None

    # Remove leading '#' and whitespace
    content = comment_line.strip()[1:].strip()

    if not content.startswith(TOMBSTONE_PREFIX):
        return None

    # Remove tombstone prefix
    content = content[len(TOMBSTONE_PREFIX):].strip()

    if '- Deprecated on:' not in content:
        return None

    try:
        parts = content.split('- Deprecated on:')
        key = parts[0].strip()
        date_str = parts[1].strip()
        deprecation_date = datetime.strptime(date_str, '%Y-%m-%d')
        return (key, deprecation_date)
    except (ValueError, IndexError):
        return None


def get_tombstoned_keys(tokens: List[Token]) -> Set[str]:
    """
    Extract all tombstoned keys from tokens.

    Args:
        tokens: List of Token objects

    Returns:
        Set of key names that are tombstoned
    """
    tombstoned = set()
    in_deprecated = False

    for token in tokens:
        if token.type == TokenType.COMMENT and DEPRECATED_MARKER in token.raw:
            in_deprecated = True
            continue

        if in_deprecated and token.type == TokenType.COMMENT:
            entry = parse_tombstone(token.raw)
            if entry:
                key, _ = entry
                tombstoned.add(key)

    return tombstoned


def find_fuzzy_tombstone_matches(
    new_keys: Set[str],
    tombstoned_keys: Set[str],
    threshold: float = FUZZY_MATCH_THRESHOLD
) -> Dict[str, str]:
    """
    Find new keys that fuzzy-match tombstoned keys.

    This helps detect when a user adds a renamed version of a deprecated key.

    Args:
        new_keys: Set of new keys being added
        tombstoned_keys: Set of tombstoned key names
        threshold: Minimum similarity ratio

    Returns:
        Dict mapping new_key -> matched_tombstone_key
    """
    matches = {}

    for new_key in new_keys:
        match = find_fuzzy_match(new_key, list(tombstoned_keys), threshold)
        if match:
            matches[new_key] = match

    return matches


def add_tombstone(content: str, key: str) -> str:
    """
    Add a tombstone for a key to .env.example content.

    Creates the deprecated section if it doesn't exist.
    Also removes the key from the active section if present.

    Args:
        content: Current .env.example content
        key: Key to tombstone

    Returns:
        Updated content with tombstone added
    """
    tokens = parse(content)
    today = datetime.now().strftime('%Y-%m-%d')

    # Remove the key from active section if it exists
    new_tokens = []
    for token in tokens:
        if token.type == TokenType.KEY_VALUE and token.key == key:
            continue  # Skip this key - it's being tombstoned
        new_tokens.append(token)

    # Check if deprecated section exists
    deprecated_index = None
    for i, token in enumerate(new_tokens):
        if token.type == TokenType.COMMENT and DEPRECATED_MARKER in token.raw:
            deprecated_index = i
            break

    tombstone_comment = f"# {TOMBSTONE_PREFIX} {key} - Deprecated on: {today}\n"

    if deprecated_index is None:
        # Create deprecated section at end
        if new_tokens and new_tokens[-1].type != TokenType.BLANK_LINE:
            new_tokens.append(Token(TokenType.BLANK_LINE, raw='\n'))

        new_tokens.append(Token(TokenType.COMMENT, raw=f"{DEPRECATED_MARKER}\n"))
        new_tokens.append(Token(TokenType.COMMENT, raw=tombstone_comment))
    else:
        # Add after the deprecated marker
        new_tokens.insert(deprecated_index + 1, Token(TokenType.COMMENT, raw=tombstone_comment))

    return write(new_tokens)


def remove_tombstone(content: str, key: str) -> str:
    """
    Remove a tombstone for a key from .env.example content.

    Also cleans up the deprecated section marker if no tombstones remain.

    Args:
        content: Current .env.example content
        key: Key to un-tombstone

    Returns:
        Updated content with tombstone removed
    """
    tokens = parse(content)

    new_tokens = []
    for token in tokens:
        if token.type == TokenType.COMMENT:
            entry = parse_tombstone(token.raw)
            if entry and entry[0] == key:
                continue  # Skip this tombstone
        new_tokens.append(token)

    # Check if any tombstones remain
    remaining_tombstones = get_tombstoned_keys(new_tokens)

    if not remaining_tombstones:
        # Remove the deprecated marker and any trailing blank lines before it
        final_tokens = []
        for token in new_tokens:
            if token.type == TokenType.COMMENT and DEPRECATED_MARKER in token.raw:
                # Remove trailing blank line before marker if present
                if final_tokens and final_tokens[-1].type == TokenType.BLANK_LINE:
                    final_tokens.pop()
                continue  # Skip the marker
            final_tokens.append(token)
        new_tokens = final_tokens

    return write(new_tokens)


class Syncer:
    """
    Manages synchronization from .env to .env.example.

    Supports two modes:
    - Single file: Traditional .env -> .env.example sync
    - Aggregated: Multiple .env* files merged with priority -> .env.example
    """

    def __init__(self, env_content: str, example_content: str):
        """
        Initialize syncer with file contents (single-file mode).

        Args:
            env_content: Content of .env file
            example_content: Content of .env.example file
        """
        self.env_tokens = parse(env_content)
        self.example_tokens = parse(example_content)

        self.env_keys = get_keys(self.env_tokens)
        self.example_keys = get_keys(self.example_tokens)

        # For aggregated mode
        self._aggregated_keys: Optional[Dict[str, "AggregatedKey"]] = None

    @classmethod
    def from_aggregated(
        cls,
        aggregated_keys: Dict[str, "AggregatedKey"],
        example_content: str
    ) -> "Syncer":
        """
        Create syncer from aggregated keys (multi-file mode).

        Args:
            aggregated_keys: Dict of key -> AggregatedKey from discovery module
            example_content: Content of .env.example file

        Returns:
            Syncer instance configured for aggregated mode
        """
        # Create instance with empty env content
        instance = cls.__new__(cls)
        instance.env_tokens = []
        instance.example_tokens = parse(example_content)

        # Convert aggregated keys to simple dict for env_keys
        instance.env_keys = {key: agg.value for key, agg in aggregated_keys.items()}
        instance.example_keys = get_keys(instance.example_tokens)

        # Store aggregated keys for source tracking
        instance._aggregated_keys = aggregated_keys

        return instance

    def get_key_source(self, key: str) -> str:
        """
        Get the source file for a key.

        Args:
            key: Environment variable key

        Returns:
            Source filename (e.g., ".env.local") or ".env" if not in aggregated mode
        """
        if self._aggregated_keys and key in self._aggregated_keys:
            return self._aggregated_keys[key].source
        return ".env"

    def sync(self, preserve_manual_edits: bool = True) -> str:
        """
        Sync .env to .env.example with fuzzy matching and tombstone support.

        Keys are added/updated from env files. Keys removed from env files
        are simply removed from .env.example (no auto-graveyard).
        Tombstoned keys are skipped and not added even if present in env files.

        Args:
            preserve_manual_edits: If True, don't overwrite values in .env.example

        Returns:
            Updated .env.example content
        """
        # Get tombstoned keys (these will be skipped)
        tombstoned_keys = get_tombstoned_keys(self.example_tokens)

        # Step 1: Update existing keys and detect renames
        updated_keys = set()
        new_tokens = []

        for token in self.example_tokens:
            if token.type == TokenType.KEY_VALUE and token.key:
                # Check if key still exists in .env
                if token.key in self.env_keys:
                    # Key exists - update placeholder if not manually edited
                    new_value = generate_placeholder(token.key, self.env_keys[token.key])

                    # Check if value is a placeholder (starts with < and ends with >)
                    is_placeholder = token.value.startswith('<') and token.value.endswith('>')
                    if preserve_manual_edits and not is_placeholder:
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
                    # Key doesn't exist in env files - check for fuzzy rename
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
                    # else: Key removed - simply don't add it (no auto-graveyard)
            else:
                # Non-key-value token - keep as-is (includes comments, blanks, tombstones)
                new_tokens.append(token)

        # Step 2: Add new keys from .env (excluding tombstoned keys)
        new_keys = set(self.env_keys.keys()) - updated_keys - tombstoned_keys

        if new_keys:
            # Add before deprecated section if it exists, otherwise at end
            deprecated_index = self._find_deprecated_index(new_tokens)

            for key in sorted(new_keys):
                value = generate_placeholder(key, self.env_keys[key])
                new_token = Token(
                    type=TokenType.KEY_VALUE,
                    raw=self._reconstruct_line(key, value, False),
                    key=key,
                    value=value,
                    has_export=False
                )

                if deprecated_index is not None:
                    new_tokens.insert(deprecated_index, new_token)
                    deprecated_index += 1
                else:
                    new_tokens.append(new_token)

        return write(new_tokens)

    def _find_deprecated_index(self, tokens: List[Token]) -> Optional[int]:
        """Find the index of the deprecated section marker."""
        for i, token in enumerate(tokens):
            if token.type == TokenType.COMMENT and DEPRECATED_MARKER in token.raw:
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
    Sync .env file to .env.example (single-file mode).

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


def sync_aggregated(
    aggregated_keys: Dict[str, "AggregatedKey"],
    example_path: str
) -> Tuple[str, "Syncer"]:
    """
    Sync aggregated keys from multiple .env* files to .env.example.

    Args:
        aggregated_keys: Dict of key -> AggregatedKey from discovery module
        example_path: Path to .env.example file

    Returns:
        Tuple of (updated .env.example content, syncer instance for source tracking)
    """
    try:
        with open(example_path, 'r') as f:
            example_content = f.read()
    except FileNotFoundError:
        example_content = ""

    syncer = Syncer.from_aggregated(aggregated_keys, example_content)
    result = syncer.sync()
    return result, syncer

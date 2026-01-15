"""
Tests for the syncer module (fuzzy matching and tombstone logic).
"""

import pytest
from datetime import datetime
from coenv.core.syncer import (
    find_fuzzy_match,
    parse_tombstone,
    get_tombstoned_keys,
    add_tombstone,
    remove_tombstone,
    Syncer,
    DEPRECATED_MARKER,
    TOMBSTONE_PREFIX,
)
from coenv.core.lexer import parse


class TestFuzzyMatching:
    """Test fuzzy key matching for rename detection."""

    def test_exact_match(self):
        """Exact matches should be found."""
        match = find_fuzzy_match("DATABASE_URL", ["DATABASE_URL", "API_KEY"])
        assert match == "DATABASE_URL"

    def test_similar_match(self):
        """Very similar keys should match."""
        match = find_fuzzy_match("DB_PASSWORD", ["DATABASE_PASSWORD", "API_KEY"])
        assert match == "DATABASE_PASSWORD"

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        match = find_fuzzy_match("api_key", ["API_KEY", "DB_URL"])
        assert match == "API_KEY"

    def test_no_match_below_threshold(self):
        """Keys below threshold should not match."""
        match = find_fuzzy_match("REDIS_URL", ["DATABASE_URL", "API_KEY"])
        # REDIS_URL is not similar enough to DATABASE_URL or API_KEY
        assert match is None

    def test_best_match_selected(self):
        """Should select the best match when multiple candidates exist."""
        match = find_fuzzy_match("DB_URL", ["DATABASE_URL", "DB_CONNECTION_URL"])
        # DB_CONNECTION_URL might be closer match
        assert match in ["DATABASE_URL", "DB_CONNECTION_URL"]

    def test_empty_candidates(self):
        """Empty candidate list should return None."""
        match = find_fuzzy_match("KEY", [])
        assert match is None


class TestTombstoneParsing:
    """Test tombstone entry parsing."""

    def test_parse_valid_tombstone(self):
        """Valid tombstone entry should be parsed."""
        comment = "# [TOMBSTONE] OLD_KEY - Deprecated on: 2024-01-15\n"
        result = parse_tombstone(comment)

        assert result is not None
        key, date = result
        assert key == "OLD_KEY"
        assert date == datetime(2024, 1, 15)

    def test_parse_invalid_format(self):
        """Invalid format should return None."""
        comment = "# Just a regular comment\n"
        result = parse_tombstone(comment)
        assert result is None

    def test_parse_old_graveyard_format(self):
        """Old graveyard format (without TOMBSTONE prefix) should return None."""
        comment = "# OLD_KEY - Removed on: 2024-01-15\n"
        result = parse_tombstone(comment)
        assert result is None

    def test_parse_non_comment(self):
        """Non-comment lines should return None."""
        line = "KEY=value\n"
        result = parse_tombstone(line)
        assert result is None

    def test_parse_malformed_date(self):
        """Malformed date should return None."""
        comment = "# [TOMBSTONE] KEY - Deprecated on: invalid-date\n"
        result = parse_tombstone(comment)
        assert result is None


class TestGetTombstonedKeys:
    """Test extracting tombstoned keys from content."""

    def test_no_tombstones(self):
        """Content without tombstones should return empty set."""
        content = "KEY1=value1\nKEY2=value2\n"
        tokens = parse(content)
        result = get_tombstoned_keys(tokens)
        assert result == set()

    def test_single_tombstone(self):
        """Should extract single tombstone."""
        content = f"""KEY1=value1

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} OLD_KEY - Deprecated on: 2024-01-15
"""
        tokens = parse(content)
        result = get_tombstoned_keys(tokens)
        assert result == {"OLD_KEY"}

    def test_multiple_tombstones(self):
        """Should extract multiple tombstones."""
        content = f"""KEY1=value1

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} OLD_KEY1 - Deprecated on: 2024-01-15
# {TOMBSTONE_PREFIX} OLD_KEY2 - Deprecated on: 2024-01-16
"""
        tokens = parse(content)
        result = get_tombstoned_keys(tokens)
        assert result == {"OLD_KEY1", "OLD_KEY2"}


class TestAddTombstone:
    """Test adding tombstones."""

    def test_add_tombstone_creates_section(self):
        """Should create deprecated section if it doesn't exist."""
        content = "KEY1=value1\n"
        result = add_tombstone(content, "OLD_KEY")

        assert DEPRECATED_MARKER in result
        assert TOMBSTONE_PREFIX in result
        assert "OLD_KEY" in result
        assert "Deprecated on:" in result

    def test_add_tombstone_removes_active_key(self):
        """Should remove key from active section when tombstoning."""
        content = "KEY1=value1\nOLD_KEY=value2\n"
        result = add_tombstone(content, "OLD_KEY")

        # OLD_KEY should not be in active section
        assert "OLD_KEY=value2" not in result
        assert "OLD_KEY=" not in result
        # But should be in tombstone
        assert f"{TOMBSTONE_PREFIX} OLD_KEY" in result

    def test_add_tombstone_appends_to_existing_section(self):
        """Should append to existing deprecated section."""
        content = f"""KEY1=value1

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} EXISTING_KEY - Deprecated on: 2024-01-15
"""
        result = add_tombstone(content, "NEW_OLD_KEY")

        assert result.count(DEPRECATED_MARKER) == 1
        assert "EXISTING_KEY" in result
        assert "NEW_OLD_KEY" in result


class TestRemoveTombstone:
    """Test removing tombstones."""

    def test_remove_tombstone(self):
        """Should remove tombstone entry."""
        content = f"""KEY1=value1

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} OLD_KEY - Deprecated on: 2024-01-15
"""
        result = remove_tombstone(content, "OLD_KEY")

        assert "OLD_KEY" not in result

    def test_remove_tombstone_preserves_others(self):
        """Should preserve other tombstones."""
        content = f"""KEY1=value1

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} KEY_TO_REMOVE - Deprecated on: 2024-01-15
# {TOMBSTONE_PREFIX} KEY_TO_KEEP - Deprecated on: 2024-01-16
"""
        result = remove_tombstone(content, "KEY_TO_REMOVE")

        assert "KEY_TO_REMOVE" not in result
        assert "KEY_TO_KEEP" in result


class TestSyncerBasic:
    """Test basic syncer functionality."""

    def test_sync_new_keys(self):
        """New keys in .env should be added to .env.example."""
        env_content = "NEW_KEY=secret_value\n"
        example_content = ""

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        assert "NEW_KEY" in result
        assert "<your_new_key>" in result

    def test_sync_updates_existing(self):
        """Existing keys should be updated with new placeholders."""
        env_content = "API_KEY=sk_test_new_secret\n"
        example_content = "API_KEY=<old_placeholder>\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        assert "API_KEY" in result
        assert "<your_api_key>" in result

    def test_sync_preserves_comments(self):
        """Comments should be preserved."""
        env_content = "KEY=value\n"
        example_content = "# Important comment\nKEY=<placeholder>\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        assert "# Important comment" in result

    def test_sync_removes_key_silently(self):
        """Removed keys should just disappear (no auto-graveyard)."""
        env_content = "NEW_KEY=value\n"
        example_content = "OLD_KEY=<placeholder>\nNEW_KEY=<placeholder>\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        # OLD_KEY should simply be gone
        assert "OLD_KEY" not in result
        # NEW_KEY should remain
        assert "NEW_KEY" in result


class TestSyncerFuzzyRename:
    """Test fuzzy rename detection during sync."""

    def test_detects_rename(self):
        """Similar keys should be detected as renames."""
        env_content = "DATABASE_PASSWORD=secret\n"
        example_content = "DB_PASSWORD=<placeholder>\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        # Should rename DB_PASSWORD to DATABASE_PASSWORD
        assert "DATABASE_PASSWORD" in result
        # Old key name should not appear
        assert "DB_PASSWORD=" not in result


class TestSyncerStickyValues:
    """Test that manual edits are preserved."""

    def test_preserves_manual_edit(self):
        """Manually edited values should not be overwritten."""
        env_content = "API_KEY=sk_test_new\n"
        example_content = "API_KEY=custom_documentation_value\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync(preserve_manual_edits=True)

        # Should preserve the custom value
        assert "custom_documentation_value" in result

    def test_updates_placeholder(self):
        """Placeholder values should be updated."""
        env_content = "API_KEY=sk_test_new\n"
        example_content = "API_KEY=<your_api_key>\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync(preserve_manual_edits=True)

        # Should update the placeholder
        assert "<your_api_key>" in result


class TestSyncerTombstones:
    """Test tombstone functionality during sync."""

    def test_tombstone_blocks_resurrection(self):
        """Tombstoned keys should not be added even if in env files."""
        env_content = "API_KEY=secret\nOTHER_KEY=value\n"
        example_content = f"""OTHER_KEY=<placeholder>

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} API_KEY - Deprecated on: 2024-01-15
"""

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        # API_KEY should NOT be added as active key (it's tombstoned)
        assert "API_KEY=" not in result
        # Tombstone should remain
        assert f"{TOMBSTONE_PREFIX} API_KEY" in result
        # OTHER_KEY should be there
        assert "OTHER_KEY=" in result

    def test_non_tombstoned_key_resurrected(self):
        """Keys not tombstoned should be resurrected normally."""
        env_content = "API_KEY=secret\n"
        # Old-style graveyard entry (not a tombstone) - should be resurrected
        example_content = f"""
{DEPRECATED_MARKER}
# API_KEY - Removed on: 2024-01-15
"""

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        # API_KEY should be added (old graveyard format doesn't block)
        assert "API_KEY=" in result

    def test_tombstone_preserved_during_sync(self):
        """Tombstones should be preserved during sync."""
        env_content = "ACTIVE_KEY=value\n"
        example_content = f"""ACTIVE_KEY=<placeholder>

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} DEAD_KEY - Deprecated on: 2024-01-15
"""

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        assert f"{TOMBSTONE_PREFIX} DEAD_KEY" in result


class TestSyncerCollaboration:
    """Test collaborative scenarios (Alice/Bob)."""

    def test_accidental_deletion_resurrected(self):
        """Accidentally deleted key should be resurrected by teammate."""
        # Alice deleted API_KEY, it just disappears from .env.example
        # Bob still has API_KEY, pulls, runs sync - it comes back
        bob_env = "API_KEY=bobs_key\nOTHER_KEY=value\n"
        alice_example = "OTHER_KEY=<placeholder>\n"  # API_KEY is gone

        syncer = Syncer(bob_env, alice_example)
        result = syncer.sync()

        # API_KEY should be added back
        assert "API_KEY=" in result
        assert "OTHER_KEY=" in result

    def test_intentional_deprecation_blocks(self):
        """Intentionally deprecated key should stay deprecated."""
        # Alice deprecated API_KEY with tombstone
        # Bob still has API_KEY, pulls, runs sync - it should NOT come back
        bob_env = "API_KEY=bobs_key\nOTHER_KEY=value\n"
        alice_example = f"""OTHER_KEY=<placeholder>

{DEPRECATED_MARKER}
# {TOMBSTONE_PREFIX} API_KEY - Deprecated on: 2024-01-15
"""

        syncer = Syncer(bob_env, alice_example)
        result = syncer.sync()

        # API_KEY should NOT be resurrected
        assert "API_KEY=" not in result
        # Tombstone should remain
        assert f"{TOMBSTONE_PREFIX} API_KEY" in result
        # OTHER_KEY should be there
        assert "OTHER_KEY=" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

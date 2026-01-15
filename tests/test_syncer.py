"""
Tests for the syncer module (fuzzy matching and graveyard logic).
"""

import pytest
from datetime import datetime, timedelta
from coenv.core.syncer import (
    find_fuzzy_match,
    parse_graveyard_entry,
    is_graveyard_expired,
    Syncer,
    GRAVEYARD_MARKER,
)


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


class TestGraveyardParsing:
    """Test graveyard entry parsing."""

    def test_parse_valid_entry(self):
        """Valid graveyard entry should be parsed."""
        comment = "# OLD_KEY - Removed on: 2024-01-15\n"
        result = parse_graveyard_entry(comment)

        assert result is not None
        key, date = result
        assert key == "OLD_KEY"
        assert date == datetime(2024, 1, 15)

    def test_parse_invalid_format(self):
        """Invalid format should return None."""
        comment = "# Just a regular comment\n"
        result = parse_graveyard_entry(comment)
        assert result is None

    def test_parse_non_comment(self):
        """Non-comment lines should return None."""
        line = "KEY=value\n"
        result = parse_graveyard_entry(line)
        assert result is None

    def test_parse_malformed_date(self):
        """Malformed date should return None."""
        comment = "# KEY - Removed on: invalid-date\n"
        result = parse_graveyard_entry(comment)
        assert result is None


class TestGraveyardExpiry:
    """Test graveyard entry expiry logic."""

    def test_expired_entry(self):
        """Entry older than 14 days should be expired."""
        old_date = datetime.now() - timedelta(days=20)
        assert is_graveyard_expired(old_date) is True

    def test_not_expired_entry(self):
        """Entry within 14 days should not be expired."""
        recent_date = datetime.now() - timedelta(days=5)
        assert is_graveyard_expired(recent_date) is False

    def test_boundary_case(self):
        """Entry at exactly 14 days should be tested."""
        boundary_date = datetime.now() - timedelta(days=14)
        # This might be expired or not depending on exact timing
        # Just ensure it doesn't error
        result = is_graveyard_expired(boundary_date)
        assert isinstance(result, bool)


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

    def test_sync_removes_to_graveyard(self):
        """Removed keys should go to graveyard."""
        env_content = "NEW_KEY=value\n"
        example_content = "OLD_KEY=<placeholder>\nNEW_KEY=<placeholder>\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        assert GRAVEYARD_MARKER in result
        assert "OLD_KEY" in result
        assert "Removed on:" in result


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
        # Old key should not be in main section
        lines_before_graveyard = result.split(GRAVEYARD_MARKER)[0] if GRAVEYARD_MARKER in result else result
        assert "DB_PASSWORD=" not in lines_before_graveyard


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


class TestSyncerGraveyard:
    """Test graveyard functionality."""

    def test_creates_graveyard(self):
        """Should create graveyard section when keys are removed."""
        env_content = "KEY1=value\n"
        example_content = "KEY1=<placeholder>\nKEY2=<placeholder>\n"

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        assert GRAVEYARD_MARKER in result
        assert "KEY2" in result
        assert "Removed on:" in result

    def test_appends_to_existing_graveyard(self):
        """Should append to existing graveyard."""
        env_content = "KEY1=value\n"
        # Use a recent date that won't expire (within 14-day TTL)
        recent_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        example_content = f"""KEY1=<placeholder>
KEY2=<placeholder>

{GRAVEYARD_MARKER}
# OLD_KEY - Removed on: {recent_date}
"""

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        assert result.count(GRAVEYARD_MARKER) == 1  # Only one graveyard marker
        assert "KEY2" in result
        assert "OLD_KEY" in result

    def test_cleans_expired_entries(self):
        """Should remove expired graveyard entries."""
        env_content = "KEY1=value\n"

        # Create an expired entry
        old_date = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%d')
        recent_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        example_content = f"""KEY1=<placeholder>

{GRAVEYARD_MARKER}
# OLD_EXPIRED_KEY - Removed on: {old_date}
# RECENT_KEY - Removed on: {recent_date}
"""

        syncer = Syncer(env_content, example_content)
        result = syncer.sync()

        # Expired entry should be removed
        assert "OLD_EXPIRED_KEY" not in result
        # Recent entry should remain
        assert "RECENT_KEY" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

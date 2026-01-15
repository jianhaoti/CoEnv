"""
Comprehensive tests for the CoEnv lexer.

Tests the critical constraint: write(parse(file)) == file (byte-identical)
"""

import pytest
from coenv.core.lexer import (
    Lexer,
    Token,
    TokenType,
    parse,
    write,
    get_keys,
    update_value,
)


class TestLexerRoundTrip:
    """Test that parsing and writing produces byte-identical output."""

    def test_empty_file(self):
        """Empty file should round-trip perfectly."""
        content = ""
        tokens = parse(content)
        assert write(tokens) == content

    def test_simple_key_value(self):
        """Simple key-value should round-trip perfectly."""
        content = "KEY=value\n"
        tokens = parse(content)
        assert write(tokens) == content

    def test_multiple_keys(self):
        """Multiple keys should round-trip perfectly."""
        content = """DATABASE_URL=postgres://localhost/db
API_KEY=secret123
DEBUG=true
"""
        tokens = parse(content)
        assert write(tokens) == content

    def test_comments(self):
        """Comments should be preserved exactly."""
        content = """# Database configuration
DATABASE_URL=postgres://localhost/db

# API settings
API_KEY=secret123
"""
        tokens = parse(content)
        assert write(tokens) == content

    def test_blank_lines(self):
        """Blank lines should be preserved."""
        content = """KEY1=value1


KEY2=value2

"""
        tokens = parse(content)
        assert write(tokens) == content

    def test_export_prefix(self):
        """Export prefix should be preserved."""
        content = """export DATABASE_URL=postgres://localhost/db
export API_KEY=secret123
NORMAL_KEY=value
"""
        tokens = parse(content)
        assert write(tokens) == content

    def test_quoted_values(self):
        """Quoted values should round-trip."""
        content = '''DATABASE_URL="postgres://localhost/db"
MESSAGE='Hello, World!'
PLAIN=value
'''
        tokens = parse(content)
        assert write(tokens) == content

    def test_values_with_spaces(self):
        """Values with spaces in quotes should round-trip."""
        content = 'MESSAGE="Hello World"\n'
        tokens = parse(content)
        assert write(tokens) == content

    def test_empty_values(self):
        """Empty values should round-trip."""
        content = """KEY1=
KEY2=value
KEY3=
"""
        tokens = parse(content)
        assert write(tokens) == content

    def test_inline_comments_preserved(self):
        """Full line is preserved as-is."""
        content = "KEY=value # inline comment\n"
        tokens = parse(content)
        assert write(tokens) == content

    def test_complex_real_world_file(self):
        """Complex real-world .env file should round-trip perfectly."""
        content = """# Application Configuration
APP_NAME=MyApp
APP_ENV=production

# Database
DATABASE_URL=postgres://user:pass@localhost:5432/mydb
DB_POOL_SIZE=10

# Redis
export REDIS_URL=redis://localhost:6379

# API Keys
STRIPE_SECRET_KEY=sk_test_123456789
OPENAI_API_KEY=sk-proj-abcdefghijklmnop

# Feature Flags
FEATURE_NEW_UI=true
FEATURE_ANALYTICS=false

# Empty values
OPTIONAL_CONFIG=

# === DEPRECATED ===
# OLD_KEY - Removed on: 2024-01-15
"""
        tokens = parse(content)
        result = write(tokens)
        assert result == content, f"Expected:\n{repr(content)}\n\nGot:\n{repr(result)}"


class TestTokenization:
    """Test token parsing and classification."""

    def test_parse_blank_line(self):
        """Blank lines should be tokenized correctly."""
        content = "\n"
        tokens = parse(content)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.BLANK_LINE
        assert tokens[0].raw == "\n"

    def test_parse_comment(self):
        """Comments should be tokenized correctly."""
        content = "# This is a comment\n"
        tokens = parse(content)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.COMMENT
        assert tokens[0].raw == "# This is a comment\n"

    def test_parse_key_value(self):
        """Key-value pairs should be tokenized correctly."""
        content = "DATABASE_URL=postgres://localhost/db\n"
        tokens = parse(content)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.KEY_VALUE
        assert tokens[0].key == "DATABASE_URL"
        assert tokens[0].value == "postgres://localhost/db"
        assert tokens[0].has_export is False

    def test_parse_export_key_value(self):
        """Exported key-value pairs should be tokenized correctly."""
        content = "export DATABASE_URL=postgres://localhost/db\n"
        tokens = parse(content)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.KEY_VALUE
        assert tokens[0].key == "DATABASE_URL"
        assert tokens[0].value == "postgres://localhost/db"
        assert tokens[0].has_export is True

    def test_parse_quoted_value(self):
        """Quoted values should be unquoted in token."""
        content = 'MESSAGE="Hello World"\n'
        tokens = parse(content)
        assert len(tokens) == 1
        assert tokens[0].value == "Hello World"

    def test_parse_single_quoted_value(self):
        """Single-quoted values should be unquoted in token."""
        content = "MESSAGE='Hello World'\n"
        tokens = parse(content)
        assert len(tokens) == 1
        assert tokens[0].value == "Hello World"

    def test_parse_empty_value(self):
        """Empty values should be handled."""
        content = "KEY=\n"
        tokens = parse(content)
        assert len(tokens) == 1
        assert tokens[0].value == ""


class TestGetKeys:
    """Test key extraction from tokens."""

    def test_get_keys_empty(self):
        """Empty content should return empty dict."""
        content = ""
        tokens = parse(content)
        keys = get_keys(tokens)
        assert keys == {}

    def test_get_keys_single(self):
        """Single key should be extracted."""
        content = "KEY=value\n"
        tokens = parse(content)
        keys = get_keys(tokens)
        assert keys == {"KEY": "value"}

    def test_get_keys_multiple(self):
        """Multiple keys should be extracted."""
        content = """KEY1=value1
KEY2=value2
KEY3=value3
"""
        tokens = parse(content)
        keys = get_keys(tokens)
        assert keys == {
            "KEY1": "value1",
            "KEY2": "value2",
            "KEY3": "value3",
        }

    def test_get_keys_ignores_comments(self):
        """Comments should be ignored."""
        content = """# Comment
KEY=value
# Another comment
"""
        tokens = parse(content)
        keys = get_keys(tokens)
        assert keys == {"KEY": "value"}

    def test_get_keys_with_export(self):
        """Exported keys should be extracted."""
        content = """export KEY1=value1
KEY2=value2
"""
        tokens = parse(content)
        keys = get_keys(tokens)
        assert keys == {
            "KEY1": "value1",
            "KEY2": "value2",
        }


class TestUpdateValue:
    """Test value updating in token stream."""

    def test_update_simple_value(self):
        """Should update a simple value."""
        content = "KEY=oldvalue\n"
        tokens = parse(content)
        updated = update_value(tokens, "KEY", "newvalue")
        result = write(updated)
        assert "KEY=newvalue\n" == result

    def test_update_preserves_other_keys(self):
        """Should preserve other keys when updating."""
        content = """KEY1=value1
KEY2=value2
KEY3=value3
"""
        tokens = parse(content)
        updated = update_value(tokens, "KEY2", "updated")
        result = write(updated)
        assert "KEY1=value1\n" in result
        assert "KEY2=updated\n" in result
        assert "KEY3=value3\n" in result

    def test_update_value_with_spaces(self):
        """Should quote values with spaces."""
        content = "KEY=value\n"
        tokens = parse(content)
        updated = update_value(tokens, "KEY", "new value with spaces")
        result = write(updated)
        assert 'KEY="new value with spaces"\n' == result

    def test_update_preserves_export(self):
        """Should preserve export prefix when updating."""
        content = "export KEY=oldvalue\n"
        tokens = parse(content)
        updated = update_value(tokens, "KEY", "newvalue")
        result = write(updated)
        assert "export KEY=newvalue\n" == result

    def test_update_nonexistent_key(self):
        """Should not modify content if key doesn't exist."""
        content = "KEY1=value1\n"
        tokens = parse(content)
        updated = update_value(tokens, "NONEXISTENT", "value")
        result = write(updated)
        assert result == content


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_no_trailing_newline(self):
        """File without trailing newline should round-trip."""
        content = "KEY=value"
        tokens = parse(content)
        assert write(tokens) == content

    def test_windows_line_endings(self):
        """Windows line endings should be preserved (if present in raw)."""
        # Note: This test depends on how splitlines(keepends=True) handles CRLF
        content = "KEY=value\r\n"
        tokens = parse(content)
        # splitlines will preserve the original line endings
        assert write(tokens) == content

    def test_value_with_equals_sign(self):
        """Values containing = should be handled."""
        content = "KEY=value=with=equals\n"
        tokens = parse(content)
        assert tokens[0].value == "value=with=equals"
        assert write(tokens) == content

    def test_key_with_underscores_and_numbers(self):
        """Keys with underscores and numbers should work."""
        content = "API_KEY_V2_123=value\n"
        tokens = parse(content)
        assert tokens[0].key == "API_KEY_V2_123"

    def test_whitespace_around_equals(self):
        """Whitespace around = should be preserved in raw."""
        content = "KEY = value\n"
        tokens = parse(content)
        # The lexer should parse this, extracting trimmed key
        assert tokens[0].key == "KEY"
        # But raw should be preserved for round-trip
        assert write(tokens) == content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

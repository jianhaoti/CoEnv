"""
Tests for exclude marker parsing.
"""

from coenv.core.excludes import parse_exclude_files


def test_parse_exclude_files_empty():
    assert parse_exclude_files("") == set()


def test_parse_exclude_files_basic():
    content = "# [EXCLUDE_FILE] .env.local\nKEY=value\n"
    assert parse_exclude_files(content) == {".env.local"}


def test_parse_exclude_files_ignores_other_comments():
    content = "# Just a comment\n# [EXCLUDE_FILE] .env.local\n"
    assert parse_exclude_files(content) == {".env.local"}

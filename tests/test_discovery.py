"""
Tests for the discovery module (multi-file discovery and aggregation).
"""

import pytest
import tempfile
from pathlib import Path
from coenv.core.discovery import (
    get_file_priority,
    discover_env_files,
    aggregate_env_files,
    get_example_path,
    AggregatedKey,
)


class TestFilePriority:
    """Test file priority ordering."""

    def test_env_local_highest_priority(self):
        """`.env.local` should have highest priority."""
        assert get_file_priority(".env.local") == 100

    def test_env_base_lowest_priority(self):
        """`.env` should have lowest priority."""
        assert get_file_priority(".env") == 0

    def test_env_mode_middle_priority(self):
        """`.env.[mode]` files should have middle priority."""
        assert get_file_priority(".env.development") == 50
        assert get_file_priority(".env.production") == 50
        assert get_file_priority(".env.test") == 50

    def test_priority_ordering(self):
        """Priority order should be .env.local > .env.[mode] > .env."""
        assert get_file_priority(".env.local") > get_file_priority(".env.development")
        assert get_file_priority(".env.development") > get_file_priority(".env")


class TestDiscoverEnvFiles:
    """Test env file discovery."""

    def test_discovers_env_file(self):
        """Should discover basic .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .env file
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("KEY=value\n")

            files = discover_env_files(tmpdir)

            assert len(files) == 1
            assert files[0].name == ".env"

    def test_discovers_multiple_files(self):
        """Should discover multiple .env* files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple env files
            (Path(tmpdir) / ".env").write_text("KEY1=value1\n")
            (Path(tmpdir) / ".env.local").write_text("KEY2=value2\n")
            (Path(tmpdir) / ".env.development").write_text("KEY3=value3\n")

            files = discover_env_files(tmpdir)

            assert len(files) == 3
            file_names = [f.name for f in files]
            assert ".env" in file_names
            assert ".env.local" in file_names
            assert ".env.development" in file_names

    def test_discovers_nested_env_files(self):
        """Should discover nested .env files when recursive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "packages" / "app"
            nested.mkdir(parents=True)
            (nested / ".env").write_text("KEY=value\n")

            files = discover_env_files(tmpdir)
            rel_paths = {path.relative_to(tmpdir) for path in files}

            assert Path("packages") / "app" / ".env" in rel_paths

    def test_excludes_files(self):
        """Should exclude specified files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".env").write_text("KEY1=value1\n")
            (Path(tmpdir) / ".env.local").write_text("KEY2=value2\n")

            files = discover_env_files(tmpdir, exclude_files={".env.local"})
            file_names = [f.name for f in files]

            assert ".env" in file_names
            assert ".env.local" not in file_names

    def test_excludes_env_example(self):
        """Should exclude .env.example file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".env").write_text("KEY=value\n")
            (Path(tmpdir) / ".env.example").write_text("KEY=<placeholder>\n")

            files = discover_env_files(tmpdir)

            assert len(files) == 1
            assert files[0].name == ".env"

    def test_sorted_by_priority(self):
        """Files should be sorted by priority (highest first)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".env").write_text("KEY=value\n")
            (Path(tmpdir) / ".env.local").write_text("KEY=value\n")
            (Path(tmpdir) / ".env.development").write_text("KEY=value\n")

            files = discover_env_files(tmpdir)

            # Should be ordered: .env.local, .env.development, .env
            assert files[0].name == ".env.local"
            assert files[-1].name == ".env"

    def test_empty_directory(self):
        """Empty directory should return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = discover_env_files(tmpdir)
            assert files == []


class TestAggregateEnvFiles:
    """Test key aggregation from multiple files."""

    def test_aggregates_from_single_file(self):
        """Should aggregate keys from single file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("KEY1=value1\nKEY2=value2\n")

            files = [env_path]
            result = aggregate_env_files(files, tmpdir)

            assert len(result) == 2
            assert "KEY1" in result
            assert "KEY2" in result
            assert result["KEY1"].value == "value1"
            assert result["KEY1"].source == ".env"

    def test_priority_merging(self):
        """Higher priority file should override lower priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files with overlapping keys
            (Path(tmpdir) / ".env").write_text("KEY=base_value\n")
            (Path(tmpdir) / ".env.local").write_text("KEY=local_value\n")

            files = discover_env_files(tmpdir)
            result = aggregate_env_files(files, tmpdir)

            # .env.local has higher priority, so its value should be used
            assert result["KEY"].value == "local_value"
            assert result["KEY"].source == ".env.local"

    def test_union_of_keys(self):
        """Should include union of all keys from all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".env").write_text("BASE_KEY=base\n")
            (Path(tmpdir) / ".env.local").write_text("LOCAL_KEY=local\n")
            (Path(tmpdir) / ".env.development").write_text("DEV_KEY=dev\n")

            files = discover_env_files(tmpdir)
            result = aggregate_env_files(files, tmpdir)

            assert len(result) == 3
            assert "BASE_KEY" in result
            assert "LOCAL_KEY" in result
            assert "DEV_KEY" in result

    def test_tracks_all_sources(self):
        """Should track all files containing each key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".env").write_text("SHARED_KEY=base\n")
            (Path(tmpdir) / ".env.local").write_text("SHARED_KEY=local\n")

            files = discover_env_files(tmpdir)
            result = aggregate_env_files(files, tmpdir)

            # Should have both sources tracked
            assert ".env.local" in result["SHARED_KEY"].all_sources
            assert ".env" in result["SHARED_KEY"].all_sources
            # Primary source should be highest priority
            assert result["SHARED_KEY"].source == ".env.local"

    def test_empty_files_list(self):
        """Empty files list should return empty dict."""
        result = aggregate_env_files([], None)
        assert result == {}


class TestGetExamplePath:
    """Test example path generation."""

    def test_returns_example_path(self):
        """Should return path to .env.example."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = get_example_path(tmpdir)
            assert path.name == ".env.example"
            assert path.parent == Path(tmpdir)


class TestAggregatedKey:
    """Test AggregatedKey dataclass."""

    def test_default_all_sources(self):
        """all_sources should default to empty list."""
        key = AggregatedKey(key="TEST", value="value", source=".env")
        assert key.all_sources == []

    def test_with_all_sources(self):
        """Should accept all_sources list."""
        key = AggregatedKey(
            key="TEST",
            value="value",
            source=".env.local",
            all_sources=[".env.local", ".env"]
        )
        assert len(key.all_sources) == 2


class TestIntegration:
    """Integration tests for discovery and aggregation."""

    def test_full_workflow(self):
        """Test complete discovery and aggregation workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a realistic multi-env setup
            (Path(tmpdir) / ".env").write_text(
                "DATABASE_URL=postgres://localhost/dev\n"
                "API_KEY=base_key\n"
                "DEBUG=false\n"
            )
            (Path(tmpdir) / ".env.local").write_text(
                "API_KEY=my_local_key\n"
                "SECRET_TOKEN=local_secret\n"
            )
            (Path(tmpdir) / ".env.development").write_text(
                "DEBUG=true\n"
                "LOG_LEVEL=debug\n"
            )
            (Path(tmpdir) / ".env.example").write_text(
                "DATABASE_URL=<your_database_url>\n"
            )

            # Discover and aggregate
            files = discover_env_files(tmpdir)
            result = aggregate_env_files(files, tmpdir)

            # Should have union of all keys (excluding .env.example)
            assert len(result) == 5
            assert "DATABASE_URL" in result
            assert "API_KEY" in result
            assert "DEBUG" in result
            assert "SECRET_TOKEN" in result
            assert "LOG_LEVEL" in result

            # Priority should be respected
            assert result["API_KEY"].value == "my_local_key"  # from .env.local
            assert result["API_KEY"].source == ".env.local"

            # .env.local > .env.development > .env for DEBUG
            # .env.local doesn't have DEBUG, so .env.development should win
            assert result["DEBUG"].value == "true"
            assert result["DEBUG"].source == ".env.development"

            # DATABASE_URL only in .env
            assert result["DATABASE_URL"].source == ".env"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

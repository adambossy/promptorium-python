from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from promptorium.cli import app


def test_cli_track_sync_list_load_delete() -> None:
    """Test basic CLI workflow: track, sync, list, load, delete."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Create source file
        prompts = Path("prompts")
        prompts.mkdir(parents=True, exist_ok=True)
        source = prompts / "onboarding.md"
        source.write_text("hello v1", encoding="utf-8")

        # Track with custom version dir
        result = runner.invoke(
            app, ["track", str(source), "--key", "onboarding", "--version-dir", "versions/system"]
        )
        assert result.exit_code == 0
        assert "Tracking 'onboarding'" in result.stdout

        # List should show the prompt
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "onboarding" in result.stdout
        assert "Source:" in result.stdout

        # Load should return content
        result = runner.invoke(app, ["load", "onboarding"])
        assert result.exit_code == 0
        assert "hello v1" in result.stdout

        # Modify source and sync
        source.write_text("hello v2", encoding="utf-8")
        result = runner.invoke(app, ["sync", "onboarding"])
        assert result.exit_code == 0
        assert "Synced 'onboarding'" in result.stdout
        assert "v1 -> v2" in result.stdout

        # Load v1
        result = runner.invoke(app, ["load", "onboarding", "--version", "1"])
        assert result.exit_code == 0
        assert "hello v1" in result.stdout

        # Load v2
        result = runner.invoke(app, ["load", "onboarding", "--version", "2"])
        assert result.exit_code == 0
        assert "hello v2" in result.stdout

        # Diff
        result = runner.invoke(app, ["diff", "onboarding", "1", "2"])
        assert result.exit_code == 0

        # Delete latest
        result = runner.invoke(app, ["delete", "onboarding"])
        assert result.exit_code == 0

        # Delete all
        result = runner.invoke(app, ["delete", "onboarding", "--all"])
        assert result.exit_code == 0


def test_cli_sync_no_changes() -> None:
    """Test sync when no changes detected."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        source = Path("prompt.md")
        source.write_text("content", encoding="utf-8")

        runner.invoke(app, ["track", str(source), "--key", "test"])

        # Sync without changes
        result = runner.invoke(app, ["sync", "test"])
        assert result.exit_code == 0
        assert "No changes" in result.stdout


def test_cli_sync_all() -> None:
    """Test sync all prompts."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        source1 = Path("prompt1.md")
        source2 = Path("prompt2.md")
        source1.write_text("one", encoding="utf-8")
        source2.write_text("two", encoding="utf-8")

        runner.invoke(app, ["track", str(source1), "--key", "one"])
        runner.invoke(app, ["track", str(source2), "--key", "two"])

        # Modify one
        source1.write_text("one modified", encoding="utf-8")

        # Sync all
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0
        assert "Synced 'one'" in result.stdout
        assert "Unchanged: 'two'" in result.stdout


def test_cli_untrack() -> None:
    """Test untrack command."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        source = Path("prompt.md")
        source.write_text("content", encoding="utf-8")

        runner.invoke(app, ["track", str(source), "--key", "test"])

        # Untrack
        result = runner.invoke(app, ["untrack", "test"])
        assert result.exit_code == 0
        assert "Untracked 'test'" in result.stdout

        # List should be empty
        result = runner.invoke(app, ["list"])
        assert "No prompts tracked" in result.stdout


def test_cli_update_via_file() -> None:
    """Test update command with --file option."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        source = Path("prompt.md")
        source.write_text("original", encoding="utf-8")

        runner.invoke(app, ["track", str(source), "--key", "test"])

        # Update via file
        update_file = Path("update.md")
        update_file.write_text("updated content", encoding="utf-8")

        result = runner.invoke(app, ["update", "test", "--file", str(update_file)])
        assert result.exit_code == 0
        assert "Updated test -> v2" in result.stdout

        # Source file should be updated
        assert source.read_text() == "updated content"


def test_cli_update_via_stdin() -> None:
    """Test update command via stdin."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        source = Path("prompt.md")
        source.write_text("original", encoding="utf-8")

        runner.invoke(app, ["track", str(source), "--key", "test"])

        # Update via stdin
        result = runner.invoke(app, ["update", "test"], input="stdin content")
        assert result.exit_code == 0
        assert "Updated test -> v2" in result.stdout

        # Source file should be updated
        assert source.read_text() == "stdin content"


def test_cli_update_mutually_exclusive_flags() -> None:
    """Test that --file and --edit flags are mutually exclusive."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        source = Path("prompt.md")
        source.write_text("content", encoding="utf-8")

        runner.invoke(app, ["track", str(source), "--key", "alpha"])
        result = runner.invoke(app, ["update", "alpha", "--file", "f.txt", "--edit"])
        # EX_USAGE
        assert result.exit_code == 64


def test_cli_track_nonexistent_file() -> None:
    """Test track with nonexistent file fails."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["track", "nonexistent.md", "--key", "test"])
        assert result.exit_code == 1
        # Error is written to stderr which is mixed into output
        assert "Source file not found" in result.output


def test_cli_track_auto_key() -> None:
    """Test track with auto-generated key."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        source = Path("prompt.md")
        source.write_text("content", encoding="utf-8")

        result = runner.invoke(app, ["track", str(source)])
        assert result.exit_code == 0
        assert "Tracking '" in result.stdout

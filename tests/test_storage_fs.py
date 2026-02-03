from __future__ import annotations

from pathlib import Path

import pytest

from promptorium.domain import PromptAlreadyExists, SourceFileNotFound
from promptorium.storage.fs import FileSystemPromptStorage


def test_track_and_versioning(tmp_path: Path) -> None:
    """Test tracking a source file and versioning."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    # Create a source file
    source = tmp_path / "prompts" / "alpha.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("hello", encoding="utf-8")

    # Track the source file
    ref = s.track_source("alpha", source, None)
    assert ref.managed_by_root is True
    assert ref.version_dir == tmp_path / ".prompts" / "alpha"
    assert ref.source_file == source

    # Initial version should be created
    assert (ref.version_dir / "1.md").exists()
    assert s.read_version("alpha", None) == "hello"

    # Modify source and sync
    source.write_text("hello world", encoding="utf-8")
    result = s.sync_from_source("alpha")
    assert result.changed is True
    assert result.old_version == 1
    assert result.new_version == 2
    assert (ref.version_dir / "2.md").exists()
    assert s.read_version("alpha", None) == "hello world"


def test_custom_version_dir_naming(tmp_path: Path) -> None:
    """Test tracking with a custom version directory."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    # Create source file
    source = tmp_path / "prompts" / "onboarding.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("v1 text", encoding="utf-8")

    # Track with custom version dir
    custom = tmp_path / "versions" / "system"
    ref = s.track_source("onboarding", source, custom)
    assert ref.managed_by_root is False
    assert ref.version_dir == custom

    # Version file should be named with key prefix
    assert (custom / "onboarding-1.md").exists()

    # Sync creates version 2
    source.write_text("v2 text", encoding="utf-8")
    s.sync_from_source("onboarding")
    assert (custom / "onboarding-2.md").exists()

    # List shows both versions
    infos = s.list_prompts()
    keys = {i.ref.key for i in infos}
    assert "onboarding" in keys
    info = next(i for i in infos if i.ref.key == "onboarding")
    assert [v.version for v in info.versions] == [1, 2]


def test_sync_no_change(tmp_path: Path) -> None:
    """Test that sync doesn't create version when unchanged."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source = tmp_path / "prompt.md"
    source.write_text("content", encoding="utf-8")
    s.track_source("test", source, None)

    # Sync without changes
    result = s.sync_from_source("test")
    assert result.changed is False
    assert result.old_version == 1
    assert result.new_version is None


def test_sync_force(tmp_path: Path) -> None:
    """Test force sync creates version even when unchanged."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source = tmp_path / "prompt.md"
    source.write_text("content", encoding="utf-8")
    s.track_source("test", source, None)

    # Force sync without changes
    result = s.sync_from_source("test", force=True)
    assert result.changed is True
    assert result.new_version == 2


def test_delete_latest_and_all(tmp_path: Path) -> None:
    """Test deleting versions."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source = tmp_path / "prompt.md"
    source.write_text("a", encoding="utf-8")
    s.track_source("alpha", source, None)

    # Create second version
    source.write_text("b", encoding="utf-8")
    s.sync_from_source("alpha")

    # Delete latest
    latest = s.delete_latest("alpha")
    assert latest.version == 2
    assert not (tmp_path / ".prompts" / "alpha" / "2.md").exists()

    # Delete all - removes from metadata
    count = s.delete_all("alpha")
    assert count == 1
    assert not (tmp_path / ".prompts" / "alpha").exists()


def test_untrack_keeps_versions(tmp_path: Path) -> None:
    """Test untrack with keep_versions=True."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source = tmp_path / "prompt.md"
    source.write_text("content", encoding="utf-8")
    s.track_source("test", source, None)

    version_dir = tmp_path / ".prompts" / "test"
    assert (version_dir / "1.md").exists()

    # Untrack but keep versions
    s.untrack("test", keep_versions=True)
    assert (version_dir / "1.md").exists()
    assert not s.key_exists("test")


def test_untrack_deletes_versions(tmp_path: Path) -> None:
    """Test untrack with keep_versions=False."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source = tmp_path / "prompt.md"
    source.write_text("content", encoding="utf-8")
    s.track_source("test", source, None)

    version_dir = tmp_path / ".prompts" / "test"
    assert (version_dir / "1.md").exists()

    # Untrack and delete versions
    s.untrack("test", keep_versions=False)
    assert not version_dir.exists()
    assert not s.key_exists("test")


def test_track_nonexistent_source_file(tmp_path: Path) -> None:
    """Test tracking a nonexistent source file raises error."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    with pytest.raises(SourceFileNotFound):
        s.track_source("test", tmp_path / "nonexistent.md", None)


def test_track_duplicate_key(tmp_path: Path) -> None:
    """Test tracking with duplicate key raises error."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source = tmp_path / "prompt.md"
    source.write_text("content", encoding="utf-8")
    s.track_source("test", source, None)

    with pytest.raises(PromptAlreadyExists):
        s.track_source("test", source, None)


def test_write_new_version_updates_source(tmp_path: Path) -> None:
    """Test write_new_version updates both source file and creates version."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source = tmp_path / "prompt.md"
    source.write_text("original", encoding="utf-8")
    s.track_source("test", source, None)

    # Write new version
    v = s.write_new_version("test", "updated content")
    assert v.version == 2

    # Source file should be updated
    assert source.read_text() == "updated content"

    # Version file should exist
    assert (tmp_path / ".prompts" / "test" / "2.md").exists()


def test_list_source_files(tmp_path: Path) -> None:
    """Test list_source_files returns tracked source paths."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source1 = tmp_path / "prompt1.md"
    source2 = tmp_path / "prompt2.md"
    source1.write_text("one", encoding="utf-8")
    source2.write_text("two", encoding="utf-8")

    s.track_source("one", source1, None)
    s.track_source("two", source2, None)

    files = s.list_source_files()
    keys = {k for k, _ in files}
    assert keys == {"one", "two"}


def test_sync_all_sources(tmp_path: Path) -> None:
    """Test sync_all_sources syncs all tracked prompts."""
    s = FileSystemPromptStorage(tmp_path)
    s.ensure_initialized()

    source1 = tmp_path / "prompt1.md"
    source2 = tmp_path / "prompt2.md"
    source1.write_text("one", encoding="utf-8")
    source2.write_text("two", encoding="utf-8")

    s.track_source("one", source1, None)
    s.track_source("two", source2, None)

    # Modify one file
    source1.write_text("one modified", encoding="utf-8")

    results = s.sync_all_sources()
    assert len(results) == 2

    changed = [r for r in results if r.changed]
    unchanged = [r for r in results if not r.changed]
    assert len(changed) == 1
    assert changed[0].key == "one"
    assert len(unchanged) == 1
    assert unchanged[0].key == "two"

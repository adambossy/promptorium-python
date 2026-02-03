from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal, overload

from .domain import (
    DiffResult,
    InvalidKey,
    NoContentProvided,
    PromptAlreadyExists,
    PromptInfo,
    PromptRef,
    PromptVersion,
    SyncResult,
)
from .storage.base import StoragePort
from .util.diff import build_inline_diff
from .util.keygen import generate_unique_key, is_valid_key


class PromptService:
    def __init__(self, storage: StoragePort):
        self.s = storage
        self.s.ensure_initialized()

    def track_source(
        self,
        source_file: Path,
        key: str | None = None,
        version_dir: Path | None = None,
    ) -> tuple[PromptRef, PromptVersion | None]:
        """
        Track a source file as a prompt.
        Creates initial version from current content.
        Returns (ref, initial_version).
        """
        if key is None:
            key = generate_unique_key(self.s)
        if not is_valid_key(key):
            raise InvalidKey(f"Invalid key: {key}")
        if self.s.key_exists(key):
            ref = self.s.get_prompt_ref(key)
            raise PromptAlreadyExists(
                f"Prompt with key '{key}' already exists with source '{ref.source_file}'. "
                "Use a different --key or untrack the existing prompt first."
            )
        ref = self.s.track_source(key, source_file, version_dir)
        # Return the initial version (version 1)
        pairs = self.s.list_prompts()
        for info in pairs:
            if info.ref.key == key and info.versions:
                return ref, info.versions[-1]
        return ref, None

    def update_prompt(self, key: str, content: str) -> PromptVersion:
        """Update prompt with new content (writes to source file and creates version)."""
        if not content:
            raise NoContentProvided("No prompt text provided.")
        # Ensure key exists
        self.s.get_prompt_ref(key)
        return self.s.write_new_version(key, content)

    def sync_prompt(self, key: str, force: bool = False) -> SyncResult:
        """Sync a single prompt from its source file."""
        return self.s.sync_from_source(key, force)

    def sync_all(self) -> list[SyncResult]:
        """Sync all source-tracked prompts."""
        return self.s.sync_all_sources()

    def untrack_source(self, key: str, keep_versions: bool = True) -> None:
        """Remove source tracking for a prompt."""
        self.s.untrack(key, keep_versions)

    def list_source_files(self) -> list[tuple[str, Path]]:
        """Return list of (key, source_file_path) tuples for all tracked prompts."""
        return self.s.list_source_files()

    def list_prompts(self) -> Sequence[PromptInfo]:
        return self.s.list_prompts()

    @overload
    def delete_prompt(self, key: str, delete_all: Literal[False] = False) -> PromptVersion: ...

    @overload
    def delete_prompt(self, key: str, delete_all: Literal[True]) -> int: ...

    def delete_prompt(self, key: str, delete_all: bool = False) -> PromptVersion | int:
        # Ensure key exists
        self.s.get_prompt_ref(key)
        return self.s.delete_all(key) if delete_all else self.s.delete_latest(key)

    def load_prompt(self, key: str, version: int | None = None) -> str:
        return self.s.read_version(key, version)

    def diff_versions(self, key: str, v1: int, v2: int, *, granularity: str = "word") -> DiffResult:
        a = self.s.read_version(key, v1)
        b = self.s.read_version(key, v2)
        g = "word" if granularity not in ("word", "char") else granularity
        segs = build_inline_diff(a, b, granularity=g)
        return DiffResult(key=key, v1=v1, v2=v2, segments=segs)

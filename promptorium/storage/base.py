from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from ..domain import PromptInfo, PromptRef, PromptVersion, SyncResult


class StoragePort(ABC):
    @abstractmethod
    def ensure_initialized(self) -> None:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def key_exists(self, key: str) -> bool:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def track_source(
        self, key: str, source_file: Path, version_dir: Path | None
    ) -> PromptRef:  # pragma: no cover - interface only
        """Track a source file as a prompt. Creates initial version."""
        ...

    @abstractmethod
    def get_prompt_ref(self, key: str) -> PromptRef:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def list_prompts(self) -> Sequence[PromptInfo]:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def write_new_version(
        self, key: str, content: str
    ) -> PromptVersion:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def delete_latest(self, key: str) -> PromptVersion:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def delete_all(self, key: str) -> int:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def read_version(
        self, key: str, version: int | None
    ) -> str:  # pragma: no cover - interface only
        ...

    @abstractmethod
    def sync_from_source(
        self, key: str, force: bool = False
    ) -> SyncResult:  # pragma: no cover - interface only
        """Create a new version if source file has changed."""
        ...

    @abstractmethod
    def sync_all_sources(self) -> list[SyncResult]:  # pragma: no cover - interface only
        """Sync all tracked source files."""
        ...

    @abstractmethod
    def list_source_files(self) -> list[tuple[str, Path]]:  # pragma: no cover - interface only
        """Return list of (key, source_file_path) tuples for all tracked prompts."""
        ...

    @abstractmethod
    def untrack(
        self, key: str, keep_versions: bool = True
    ) -> None:  # pragma: no cover - interface only
        """Remove tracking for a prompt. Optionally delete version files."""
        ...

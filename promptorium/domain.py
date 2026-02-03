from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class PromptRef:
    key: str
    source_file: Path  # path to source of truth file
    version_dir: Path  # where versions live
    managed_by_root: bool  # version_dir under <repo-root>/.prompts ?


@dataclass(frozen=True)
class PromptVersion:
    key: str
    version: int
    path: Path


@dataclass(frozen=True)
class PromptInfo:
    ref: PromptRef
    versions: Sequence[PromptVersion]  # sorted ascending


DiffOp = Literal["equal", "insert", "delete"]


@dataclass(frozen=True)
class DiffSegment:
    op: DiffOp
    text: str


@dataclass(frozen=True)
class DiffResult:
    key: str
    v1: int
    v2: int
    segments: Sequence[DiffSegment]


@dataclass(frozen=True)
class SyncResult:
    key: str
    changed: bool
    old_version: int | None
    new_version: int | None
    message: str


class PromptError(Exception): ...


class PromptAlreadyExists(PromptError): ...


class PromptNotFound(PromptError): ...


class VersionNotFound(PromptError): ...


class InvalidKey(PromptError): ...


class NoContentProvided(PromptError): ...


class SourceFileNotFound(PromptError): ...

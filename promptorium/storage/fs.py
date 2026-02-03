from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..domain import (
    PromptAlreadyExists,
    PromptInfo,
    PromptNotFound,
    PromptRef,
    PromptVersion,
    SourceFileNotFound,
    SyncResult,
    VersionNotFound,
)
from ..util.io_safety import atomic_write_text
from .base import StoragePort

_SCHEMA_VERSION = 2


@dataclass
class _PromptConfig:
    source_file: str  # relative or absolute path
    version_dir: str  # relative or absolute path
    last_hash: str | None
    last_version: int


@dataclass
class _Meta:
    schema: int
    prompts: dict[str, _PromptConfig]


class FileSystemPromptStorage(StoragePort):
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self.root = self.repo_root / ".prompts"
        self._meta_path = self.root / "_meta.json"

    # --- helpers ---
    def _load_meta(self) -> _Meta:
        if not self._meta_path.exists():
            return _Meta(schema=_SCHEMA_VERSION, prompts={})
        data = json.loads(self._meta_path.read_text(encoding="utf-8"))
        schema = int(data.get("schema", 0))
        if schema != _SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema version {schema}. Expected {_SCHEMA_VERSION}. "
                "Run the migration script to upgrade."
            )
        prompts: dict[str, _PromptConfig] = {}
        for key, cfg in data.get("prompts", {}).items():
            prompts[key] = _PromptConfig(
                source_file=cfg["source_file"],
                version_dir=cfg["version_dir"],
                last_hash=cfg.get("last_hash"),
                last_version=cfg.get("last_version", 0),
            )
        return _Meta(schema=schema, prompts=prompts)

    def _save_meta(self, meta: _Meta) -> None:
        prompts_data = {}
        for key, cfg in meta.prompts.items():
            prompts_data[key] = {
                "source_file": cfg.source_file,
                "version_dir": cfg.version_dir,
                "last_hash": cfg.last_hash,
                "last_version": cfg.last_version,
            }
        payload = {"schema": meta.schema, "prompts": prompts_data}
        atomic_write_text(self._meta_path, json.dumps(payload, indent=2) + "\n")

    def _resolve_path(self, value: str) -> Path:
        """Resolve a stored path to an absolute path."""
        p = Path(value)
        if p.is_absolute():
            return p
        return (self.repo_root / p).resolve()

    def _store_path(self, path: Path) -> str:
        """Store a path as relative if possible, otherwise absolute."""
        try:
            rel = path.resolve().relative_to(self.repo_root)
            return rel.as_posix()
        except ValueError:
            return str(path.resolve())

    def _default_version_dir(self, key: str) -> Path:
        return self.root / key

    def _is_managed_by_root(self, version_dir: Path) -> bool:
        try:
            version_dir.resolve().relative_to(self.root)
            return True
        except ValueError:
            return False

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

    def _scan_versions(
        self, key: str, version_dir: Path, managed_by_root: bool
    ) -> list[tuple[int, Path]]:
        """Scan a directory for version files."""
        if not version_dir.exists():
            return []
        versions: list[tuple[int, Path]] = []
        if managed_by_root:
            # Default: <version_dir>/<n>.md
            for p in version_dir.iterdir():
                if p.is_file() and re.fullmatch(r"\d+\.md", p.name):
                    n = int(p.stem)
                    versions.append((n, p))
        else:
            # Custom: <version_dir>/<key>-<n>.md
            pattern = re.compile(rf"^{re.escape(key)}-(\d+)\.md$")
            for p in version_dir.iterdir():
                if p.is_file():
                    m = pattern.fullmatch(p.name)
                    if m:
                        n = int(m.group(1))
                        versions.append((n, p))
        versions.sort(key=lambda t: t[0])
        return versions

    def _next_version(self, key: str, version_dir: Path, managed_by_root: bool) -> int:
        pairs = self._scan_versions(key, version_dir, managed_by_root)
        return (pairs[-1][0] + 1) if pairs else 1

    def _version_path(
        self, key: str, version: int, version_dir: Path, managed_by_root: bool
    ) -> Path:
        if managed_by_root:
            return version_dir / f"{version}.md"
        return version_dir / f"{key}-{version}.md"

    # --- API ---
    def ensure_initialized(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self._meta_path.exists():
            self._save_meta(_Meta(schema=_SCHEMA_VERSION, prompts={}))

    def key_exists(self, key: str) -> bool:
        meta = self._load_meta()
        return key in meta.prompts

    def track_source(self, key: str, source_file: Path, version_dir: Path | None) -> PromptRef:
        self.ensure_initialized()
        meta = self._load_meta()

        if key in meta.prompts:
            raise PromptAlreadyExists(f"Prompt key '{key}' already exists.")

        # Resolve source file
        source_path = (
            (self.repo_root / source_file).resolve()
            if not source_file.is_absolute()
            else source_file.resolve()
        )
        if not source_path.exists():
            raise SourceFileNotFound(f"Source file not found: {source_path}")

        # Resolve version directory
        if version_dir is None:
            ver_dir = self._default_version_dir(key)
        else:
            ver_dir = (
                (self.repo_root / version_dir).resolve()
                if not version_dir.is_absolute()
                else version_dir.resolve()
            )
        ver_dir.mkdir(parents=True, exist_ok=True)

        managed_by_root = self._is_managed_by_root(ver_dir)

        # Read source content and create initial version
        content = source_path.read_text(encoding="utf-8")
        content_hash = self._compute_hash(content)
        next_ver = self._next_version(key, ver_dir, managed_by_root)
        version_path = self._version_path(key, next_ver, ver_dir, managed_by_root)
        atomic_write_text(version_path, content)

        # Save metadata
        meta.prompts[key] = _PromptConfig(
            source_file=self._store_path(source_path),
            version_dir=self._store_path(ver_dir),
            last_hash=content_hash,
            last_version=next_ver,
        )
        self._save_meta(meta)

        return PromptRef(
            key=key,
            source_file=source_path,
            version_dir=ver_dir,
            managed_by_root=managed_by_root,
        )

    def get_prompt_ref(self, key: str) -> PromptRef:
        meta = self._load_meta()
        if key not in meta.prompts:
            raise PromptNotFound(key)
        cfg = meta.prompts[key]
        source_path = self._resolve_path(cfg.source_file)
        ver_dir = self._resolve_path(cfg.version_dir)
        return PromptRef(
            key=key,
            source_file=source_path,
            version_dir=ver_dir,
            managed_by_root=self._is_managed_by_root(ver_dir),
        )

    def list_prompts(self) -> Sequence[PromptInfo]:
        self.ensure_initialized()
        meta = self._load_meta()

        infos: list[PromptInfo] = []
        for key in sorted(meta.prompts.keys()):
            cfg = meta.prompts[key]
            source_path = self._resolve_path(cfg.source_file)
            ver_dir = self._resolve_path(cfg.version_dir)
            managed_by_root = self._is_managed_by_root(ver_dir)
            ref = PromptRef(
                key=key,
                source_file=source_path,
                version_dir=ver_dir,
                managed_by_root=managed_by_root,
            )
            pairs = self._scan_versions(key, ver_dir, managed_by_root)
            versions = [PromptVersion(key=key, version=n, path=path) for n, path in pairs]
            infos.append(PromptInfo(ref=ref, versions=versions))
        return infos

    def write_new_version(self, key: str, content: str) -> PromptVersion:
        """Write a new version from provided content (updates source file too)."""
        ref = self.get_prompt_ref(key)
        meta = self._load_meta()
        cfg = meta.prompts[key]

        # Write to source file
        atomic_write_text(ref.source_file, content)

        # Create new version
        next_ver = self._next_version(key, ref.version_dir, ref.managed_by_root)
        version_path = self._version_path(key, next_ver, ref.version_dir, ref.managed_by_root)
        atomic_write_text(version_path, content)

        # Update metadata
        cfg.last_hash = self._compute_hash(content)
        cfg.last_version = next_ver
        self._save_meta(meta)

        return PromptVersion(key=key, version=next_ver, path=version_path)

    def delete_latest(self, key: str) -> PromptVersion:
        ref = self.get_prompt_ref(key)
        pairs = self._scan_versions(key, ref.version_dir, ref.managed_by_root)
        if not pairs:
            raise VersionNotFound(f"No versions for key: {key}")
        ver, path = pairs[-1]
        path.unlink(missing_ok=False)

        # Update last_version in metadata
        meta = self._load_meta()
        if pairs[:-1]:
            meta.prompts[key].last_version = pairs[-2][0]
        else:
            meta.prompts[key].last_version = 0
        self._save_meta(meta)

        return PromptVersion(key=key, version=ver, path=path)

    def delete_all(self, key: str) -> int:
        ref = self.get_prompt_ref(key)
        pairs = self._scan_versions(key, ref.version_dir, ref.managed_by_root)
        for _, p in pairs:
            p.unlink(missing_ok=False)
        # Try to remove directory if managed by root
        if ref.managed_by_root:
            try:
                ref.version_dir.rmdir()
            except OSError:
                pass
        # Remove from metadata
        meta = self._load_meta()
        del meta.prompts[key]
        self._save_meta(meta)
        return len(pairs)

    def read_version(self, key: str, version: int | None) -> str:
        ref = self.get_prompt_ref(key)
        pairs = self._scan_versions(key, ref.version_dir, ref.managed_by_root)
        if not pairs:
            raise VersionNotFound(f"No versions for key: {key}")
        if version is None:
            _, path = pairs[-1]
            return path.read_text(encoding="utf-8")
        # Find specific version
        for v, path in pairs:
            if v == version:
                return path.read_text(encoding="utf-8")
        raise VersionNotFound(f"Version {version} not found for key: {key}")

    def sync_from_source(self, key: str, force: bool = False) -> SyncResult:
        ref = self.get_prompt_ref(key)
        meta = self._load_meta()
        cfg = meta.prompts[key]

        if not ref.source_file.exists():
            raise SourceFileNotFound(f"Source file not found: {ref.source_file}")

        content = ref.source_file.read_text(encoding="utf-8")
        current_hash = self._compute_hash(content)

        if not force and current_hash == cfg.last_hash:
            return SyncResult(
                key=key,
                changed=False,
                old_version=cfg.last_version,
                new_version=None,
                message=f"No changes detected for '{key}'",
            )

        old_version = cfg.last_version
        next_ver = self._next_version(key, ref.version_dir, ref.managed_by_root)
        version_path = self._version_path(key, next_ver, ref.version_dir, ref.managed_by_root)
        atomic_write_text(version_path, content)

        cfg.last_hash = current_hash
        cfg.last_version = next_ver
        self._save_meta(meta)

        return SyncResult(
            key=key,
            changed=True,
            old_version=old_version,
            new_version=next_ver,
            message=f"Synced '{key}': v{old_version} -> v{next_ver}",
        )

    def sync_all_sources(self) -> list[SyncResult]:
        meta = self._load_meta()
        results: list[SyncResult] = []
        for key in meta.prompts:
            try:
                result = self.sync_from_source(key)
                results.append(result)
            except SourceFileNotFound as e:
                results.append(
                    SyncResult(
                        key=key,
                        changed=False,
                        old_version=None,
                        new_version=None,
                        message=str(e),
                    )
                )
        return results

    def list_source_files(self) -> list[tuple[str, Path]]:
        meta = self._load_meta()
        return [(key, self._resolve_path(cfg.source_file)) for key, cfg in meta.prompts.items()]

    def untrack(self, key: str, keep_versions: bool = True) -> None:
        if not self.key_exists(key):
            raise PromptNotFound(key)

        if not keep_versions:
            self.delete_all(key)
        else:
            meta = self._load_meta()
            del meta.prompts[key]
            self._save_meta(meta)

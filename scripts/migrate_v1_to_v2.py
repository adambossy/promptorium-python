#!/usr/bin/env python3
"""Migrate promptorium from schema v1 to v2.

This script migrates existing prompts from the old versioning model (schema v1)
to the new source-of-truth model (schema v2).

Usage:
    python scripts/migrate_v1_to_v2.py [--repo-root /path/to/repo]

For each existing prompt:
1. Reads current v1 metadata and version files
2. Creates new v2 metadata structure
3. Prompts user to specify source file path (or creates one from latest version)
4. Writes new _meta.json in v2 format
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def scan_default_versions(key: str, version_dir: Path) -> list[tuple[int, Path]]:
    """Scan for version files in default-managed format: <n>.md"""
    versions: list[tuple[int, Path]] = []
    if not version_dir.exists():
        return []
    for p in version_dir.iterdir():
        if p.is_file() and re.fullmatch(r"\d+\.md", p.name):
            n = int(p.stem)
            versions.append((n, p))
    versions.sort(key=lambda t: t[0])
    return versions


def scan_custom_versions(key: str, version_dir: Path) -> list[tuple[int, Path]]:
    """Scan for version files in custom-managed format: <key>-<n>.md"""
    pattern = re.compile(rf"^{re.escape(key)}-(\d+)\.md$")
    versions: list[tuple[int, Path]] = []
    if not version_dir.exists():
        return []
    for p in version_dir.iterdir():
        if p.is_file():
            m = pattern.fullmatch(p.name)
            if m:
                n = int(m.group(1))
                versions.append((n, p))
    versions.sort(key=lambda t: t[0])
    return versions


def migrate(repo_root: Path, prompts_dir: Path | None = None) -> None:
    """Migrate from v1 to v2 schema."""
    prompts_root = repo_root / ".prompts"
    meta_path = prompts_root / "_meta.json"

    if not meta_path.exists():
        print(f"No _meta.json found at {meta_path}. Nothing to migrate.")
        return

    # Back up existing metadata
    backup_path = prompts_root / "_meta.json.v1.bak"
    shutil.copy(meta_path, backup_path)
    print(f"Backed up existing metadata to {backup_path}")

    # Load v1 metadata
    with open(meta_path, encoding="utf-8") as f:
        v1_data = json.load(f)

    schema = v1_data.get("schema", 1)
    if schema >= 2:
        print(f"Metadata is already schema version {schema}. Nothing to migrate.")
        return

    custom_dirs = v1_data.get("custom_dirs", {})

    # Discover all prompts
    prompts_to_migrate: list[dict] = []

    # Default-managed prompts (directories under .prompts/)
    if prompts_root.exists():
        for p in prompts_root.iterdir():
            if p.is_dir() and p.name != "__pycache__" and not p.name.startswith("_"):
                key = p.name
                if key not in custom_dirs:
                    versions = scan_default_versions(key, p)
                    if versions:
                        prompts_to_migrate.append({
                            "key": key,
                            "version_dir": p,
                            "versions": versions,
                            "managed_by_root": True,
                        })

    # Custom-managed prompts
    for key, dir_val in custom_dirs.items():
        dir_path = Path(dir_val)
        if not dir_path.is_absolute():
            dir_path = repo_root / dir_path
        versions = scan_custom_versions(key, dir_path)
        if versions:
            prompts_to_migrate.append({
                "key": key,
                "version_dir": dir_path,
                "versions": versions,
                "managed_by_root": False,
            })

    if not prompts_to_migrate:
        print("No prompts found to migrate.")
        # Still create v2 metadata with empty prompts
        v2_data = {"schema": 2, "prompts": {}}
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(v2_data, f, indent=2)
            f.write("\n")
        print("Created empty v2 metadata.")
        return

    print(f"\nFound {len(prompts_to_migrate)} prompt(s) to migrate:\n")

    # Determine source file directory
    if prompts_dir is None:
        prompts_dir = repo_root / "prompts"

    prompts_dir.mkdir(parents=True, exist_ok=True)

    v2_prompts: dict[str, dict] = {}

    for prompt_info in prompts_to_migrate:
        key = prompt_info["key"]
        version_dir = prompt_info["version_dir"]
        versions = prompt_info["versions"]
        latest_version, latest_path = versions[-1]

        print(f"Prompt: {key}")
        print(f"  Version dir: {version_dir}")
        print(f"  Latest version: v{latest_version} at {latest_path}")

        # Determine source file location
        source_file = prompts_dir / f"{key}.md"

        # Check if source file already exists
        if source_file.exists():
            print(f"  Source file already exists: {source_file}")
            response = input("  Use existing file? [Y/n]: ").strip().lower()
            if response in ("n", "no"):
                custom_path = input("  Enter custom source file path: ").strip()
                source_file = Path(custom_path)
                if not source_file.is_absolute():
                    source_file = repo_root / source_file
        else:
            # Create source file from latest version
            print(f"  Creating source file: {source_file}")
            content = latest_path.read_text(encoding="utf-8")
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text(content, encoding="utf-8")

        # Compute hash
        content = source_file.read_text(encoding="utf-8")
        content_hash = compute_hash(content)

        # Store relative paths if possible
        try:
            source_rel = source_file.resolve().relative_to(repo_root)
            source_str = source_rel.as_posix()
        except ValueError:
            source_str = str(source_file.resolve())

        try:
            version_rel = version_dir.resolve().relative_to(repo_root)
            version_str = version_rel.as_posix()
        except ValueError:
            version_str = str(version_dir.resolve())

        v2_prompts[key] = {
            "source_file": source_str,
            "version_dir": version_str,
            "last_hash": content_hash,
            "last_version": latest_version,
        }

        print(f"  Migrated to v2 format\n")

    # Write v2 metadata
    v2_data = {"schema": 2, "prompts": v2_prompts}
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(v2_data, f, indent=2)
        f.write("\n")

    print(f"Migration complete! Updated {meta_path}")
    print(f"Backup saved at {backup_path}")
    print(f"\nMigrated {len(v2_prompts)} prompt(s) to v2 schema.")
    print("\nSource files created in:", prompts_dir)
    print("\nNext steps:")
    print("  1. Review the source files in", prompts_dir)
    print("  2. Add source files to git: git add", prompts_dir)
    print("  3. Test with: prompts list")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate promptorium from v1 to v2 schema"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (default: current directory)",
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=None,
        help="Directory for source files (default: <repo-root>/prompts)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root
    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = repo_root.resolve()

    print(f"Migrating promptorium in: {repo_root}")
    migrate(repo_root, args.prompts_dir)


if __name__ == "__main__":
    main()

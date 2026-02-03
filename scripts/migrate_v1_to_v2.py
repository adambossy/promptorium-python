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
from pathlib import Path

from promptorium.migration import migrate


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
    migrate(
        repo_root=repo_root,
        from_version=1,
        to_version=2,
        prompts_dir=args.prompts_dir,
        interactive=True,
    )


if __name__ == "__main__":
    main()

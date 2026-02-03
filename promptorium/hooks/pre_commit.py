#!/usr/bin/env python3
"""Pre-commit hook for promptorium source file versioning.

This hook detects changes to tracked source files and auto-versions them.
It operates in warn-only mode (exit 0), printing warnings but not blocking commits.

Usage:
    Add to .pre-commit-config.yaml:

    repos:
      - repo: local
        hooks:
          - id: promptorium-sync
            name: Promptorium Source Sync
            entry: python -m promptorium.hooks.pre_commit
            language: python
            pass_filenames: false
            always_run: true
            stages: [pre-commit]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def get_staged_files(repo_root: Path) -> set[Path]:
    """Get the set of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root,
        )
        return {(repo_root / f.strip()).resolve() for f in result.stdout.splitlines() if f.strip()}
    except subprocess.CalledProcessError:
        return set()


def main() -> int:
    """Main entry point for pre-commit hook."""
    try:
        # Import here to avoid issues if promptorium isn't installed
        from ..services import PromptService
        from ..storage.fs import FileSystemPromptStorage
        from ..util.repo_root import find_repo_root

        repo_root = find_repo_root()
        storage = FileSystemPromptStorage(repo_root)
        svc = PromptService(storage)

        # Get staged files
        staged = get_staged_files(repo_root)
        if not staged:
            return 0

        # Get tracked source files
        source_files = svc.list_source_files()
        if not source_files:
            return 0

        # Find staged source files that need versioning
        from ..domain import SyncResult

        needs_versioning: list[tuple[str, Path, SyncResult]] = []
        for key, source_path in source_files:
            resolved = source_path.resolve()
            if resolved in staged:
                # Sync to create new version
                result = svc.sync_prompt(key, force=False)
                if result.changed:
                    needs_versioning.append((key, source_path, result))

        if needs_versioning:
            print("promptorium: The following source files have changes:")
            for key, path, result in needs_versioning:
                print(f"  - {key}: {path} (v{result.old_version} -> v{result.new_version})")
            print()
            print("New versions have been created. You may want to:")
            print("  1. Stage the new version files: git add .prompts/")
            print("  2. Or run: prompts sync")
            print()

        # Warn-only mode: exit 0 to not block commit
        return 0

    except Exception as e:
        print(f"promptorium pre-commit hook warning: {e}", file=sys.stderr)
        # Don't block commit on errors
        return 0


if __name__ == "__main__":
    sys.exit(main())

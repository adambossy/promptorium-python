"""MCP server for promptorium - exposes prompt management as MCP tools."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .domain import PromptError
from .services import PromptService
from .storage.fs import FileSystemPromptStorage
from .util.repo_root import find_repo_root

mcp = FastMCP("promptorium")


def _get_service() -> PromptService:
    """Get a configured PromptService instance."""
    storage = FileSystemPromptStorage(find_repo_root())
    return PromptService(storage)


@mcp.tool()
def list_prompts() -> str:
    """List all tracked prompts with their versions.

    Returns a formatted string showing all prompt keys, their source files,
    version directories, and available versions.
    """
    try:
        svc = _get_service()
        infos = svc.list_prompts()
        if not infos:
            return "No prompts tracked."

        lines = []
        for info in infos:
            lines.append(f"Key: {info.ref.key}")
            lines.append(f"  Source: {info.ref.source_file}")
            lines.append(f"  Versions: {info.ref.version_dir}")
            for v in info.versions:
                lines.append(f"    - v{v.version}: {v.path}")
        return "\n".join(lines)
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def load_prompt(key: str, version: int | None = None) -> str:
    """Load the content of a prompt.

    Args:
        key: The prompt key to load
        version: Specific version number (latest if not specified)

    Returns:
        The prompt content as text
    """
    try:
        svc = _get_service()
        return svc.load_prompt(key, version)
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def track_prompt(
    source_file: str,
    key: str | None = None,
    version_dir: str | None = None,
) -> str:
    """Track an existing file as a prompt source.

    Args:
        source_file: Path to the source file to track (relative to repo root)
        key: Human-readable key (auto-generated if not provided)
        version_dir: Custom directory for versions (optional)

    Returns:
        Confirmation message with the created prompt details
    """
    try:
        svc = _get_service()
        source_path = Path(source_file)
        dir_path = Path(version_dir) if version_dir else None

        ref, initial_ver = svc.track_source(source_path, key, dir_path)
        msg = f"Tracking '{ref.key}' from {ref.source_file}"
        if initial_ver:
            msg += f" (initial version: v{initial_ver.version})"
        return msg
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def update_prompt(key: str, content: str) -> str:
    """Update a prompt with new content.

    Writes to the source file and creates a new version.

    Args:
        key: The prompt key to update
        content: New content for the prompt

    Returns:
        Confirmation message with the new version number
    """
    try:
        svc = _get_service()
        v = svc.update_prompt(key, content)
        return f"Updated {v.key} -> v{v.version}"
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def sync_prompts(key: str | None = None, force: bool = False) -> str:
    """Sync source files to create new versions if changed.

    Args:
        key: Specific key to sync (all if not provided)
        force: Create version even if unchanged

    Returns:
        Summary of sync results
    """
    try:
        svc = _get_service()

        if key:
            result = svc.sync_prompt(key, force)
            if result.changed:
                return f"Synced '{key}': v{result.old_version} -> v{result.new_version}"
            return f"No changes for '{key}' (at v{result.old_version})"
        else:
            results = svc.sync_all()
            if not results:
                return "No source-tracked prompts found"
            lines = []
            for r in results:
                if r.changed:
                    lines.append(f"Synced '{r.key}': v{r.old_version} -> v{r.new_version}")
                else:
                    lines.append(f"Unchanged: '{r.key}' (at v{r.old_version})")
            return "\n".join(lines)
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def delete_prompt(key: str, all_versions: bool = False) -> str:
    """Delete a prompt or its latest version.

    Args:
        key: The prompt key to delete
        all_versions: If True, delete all versions; otherwise just latest

    Returns:
        Confirmation message
    """
    try:
        svc = _get_service()
        if all_versions:
            n = svc.delete_prompt(key, delete_all=True)
            return f"Deleted {n} version(s) for '{key}'"
        else:
            v = svc.delete_prompt(key, delete_all=False)
            return f"Deleted v{v.version} for '{key}'"
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def untrack_prompt(key: str, keep_versions: bool = True) -> str:
    """Stop tracking a source file.

    Args:
        key: The prompt key to untrack
        keep_versions: Whether to keep version files (default True)

    Returns:
        Confirmation message
    """
    try:
        svc = _get_service()
        svc.untrack_source(key, keep_versions)
        if keep_versions:
            return f"Untracked '{key}' (versions kept)"
        return f"Untracked '{key}' (versions deleted)"
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def diff_versions(key: str, v1: int, v2: int, granularity: str = "word") -> str:
    """Show differences between two versions of a prompt.

    Args:
        key: The prompt key
        v1: First version number
        v2: Second version number
        granularity: 'word' or 'char' for diff granularity

    Returns:
        Formatted diff output showing insertions and deletions
    """
    try:
        svc = _get_service()
        result = svc.diff_versions(key, v1, v2, granularity=granularity)

        lines = [f"Diff {key} v{v1} -> v{v2}:", ""]
        parts = []
        for seg in result.segments:
            if seg.op == "equal":
                parts.append(seg.text)
            elif seg.op == "insert":
                parts.append(f"[+{seg.text}]")
            elif seg.op == "delete":
                parts.append(f"[-{seg.text}]")
        lines.append("".join(parts))
        return "\n".join(lines)
    except PromptError as e:
        return f"Error: {e}"


@mcp.tool()
def migrate_schema(
    from_version: int = 1,
    to_version: int = 2,
    prompts_dir: str | None = None,
) -> str:
    """Migrate prompt metadata between schema versions.

    Args:
        from_version: Source schema version (default: 1)
        to_version: Target schema version (default: 2)
        prompts_dir: Directory for source files (default: prompts/)

    Returns:
        Summary of migration results
    """
    from .migration import migrate as do_migrate

    try:
        result = do_migrate(
            repo_root=find_repo_root(),
            from_version=from_version,
            to_version=to_version,
            prompts_dir=Path(prompts_dir) if prompts_dir else None,
            interactive=False,  # Non-interactive for MCP
        )
        return f"Migrated {result['migrated']} prompt(s) from v{from_version} to v{to_version}"
    except ValueError as e:
        return f"Error: {e}"


def run_server() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    run_server()

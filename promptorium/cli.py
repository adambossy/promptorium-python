from __future__ import annotations

import sys
from pathlib import Path

import typer

from .domain import PromptError
from .services import PromptService
from .storage.fs import FileSystemPromptStorage
from .util import editor as editor_util
from .util.render import render_diff_to_console
from .util.repo_root import find_repo_root

app = typer.Typer(add_completion=False)


def _service() -> PromptService:
    storage = FileSystemPromptStorage(find_repo_root())
    return PromptService(storage)


@app.command()
def track(
    source: Path = typer.Argument(..., help="Path to the source file to track"),
    key: str | None = typer.Option(None, "--key", help="Key for the prompt"),
    version_dir: Path | None = typer.Option(None, "--version-dir", help="Custom version dir"),
) -> None:
    """Track an existing file as a prompt source."""
    try:
        ref, initial_ver = _service().track_source(source, key, version_dir)
        typer.echo(f"Tracking '{ref.key}' from {ref.source_file}")
        if initial_ver:
            typer.echo(f"  Initial version: v{initial_ver.version}")
    except PromptError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def sync(
    key: str | None = typer.Argument(None, help="Key to sync (or all if omitted)"),
    force: bool = typer.Option(False, "--force", help="Create version even if unchanged"),
) -> None:
    """Sync source file(s) to create new versions if changed."""
    svc = _service()
    try:
        if key:
            result = svc.sync_prompt(key, force)
            if result.changed:
                typer.echo(f"Synced '{key}': v{result.old_version} -> v{result.new_version}")
            else:
                typer.echo(f"No changes for '{key}' (at v{result.old_version})")
        else:
            results = svc.sync_all()
            if not results:
                typer.echo("No source-tracked prompts found.")
                return
            for r in results:
                if r.changed:
                    typer.echo(f"Synced '{r.key}': v{r.old_version} -> v{r.new_version}")
                else:
                    typer.echo(f"Unchanged: '{r.key}' (at v{r.old_version})")
    except PromptError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def untrack(
    key: str = typer.Argument(..., help="Key to untrack"),
    keep_versions: bool = typer.Option(True, "--keep-versions/--delete-versions"),
) -> None:
    """Stop tracking a source file (optionally keep version history)."""
    try:
        _service().untrack_source(key, keep_versions)
        if keep_versions:
            typer.echo(f"Untracked '{key}' (versions kept)")
        else:
            typer.echo(f"Untracked '{key}' (versions deleted)")
    except PromptError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def update(
    key: str,
    file: Path | None = typer.Option(None, "--file", help="Read prompt text from file"),
    edit: bool = typer.Option(False, "--edit", help="Open $EDITOR to edit the prompt text"),
) -> None:
    """Update a prompt with new content (writes to source file and creates version)."""
    svc = _service()
    try:
        if file is not None and edit:
            typer.secho("Use either --file or --edit, not both.", err=True, fg=typer.colors.RED)
            raise typer.Exit(64)

        if file is not None:
            text = file.read_text(encoding="utf-8")
        elif edit:
            try:
                seed = svc.load_prompt(key)
            except PromptError:
                seed = ""
            text = editor_util.open_in_editor(seed)
        else:
            if sys.stdin.isatty():
                typer.secho(
                    "Provide content via --file, --edit, or STDIN.", err=True, fg=typer.colors.RED
                )
                raise typer.Exit(64)
            text = sys.stdin.read()

        v = svc.update_prompt(key, text)
        typer.echo(f"Updated {v.key} -> v{v.version} ({v.path})")
    except PromptError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command("list")
def list_() -> None:
    """List all tracked prompts with their source files and versions."""
    infos = _service().list_prompts()
    if not infos:
        typer.echo("No prompts tracked.")
        raise typer.Exit()
    for info in infos:
        typer.echo(f"\n{info.ref.key}")
        typer.echo(f"  Source: {info.ref.source_file}")
        typer.echo(f"  Versions: {info.ref.version_dir}")
        for v in info.versions:
            typer.echo(f"    - v{v.version}: {v.path}")
    typer.echo("")


@app.command()
def delete(key: str, all: bool = typer.Option(False, "--all")) -> None:  # noqa: A002 - match CLI spec
    """Delete a prompt's versions (latest or all)."""
    svc = _service()
    try:
        if all:
            n = svc.delete_prompt(key, delete_all=True)
            typer.echo(f"Deleted {n} version(s) for '{key}'.")
        else:
            v = svc.delete_prompt(key, delete_all=False)
            typer.echo(f"Deleted latest version v{v.version} for '{key}'.")
    except PromptError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def load(key: str, version: int | None = typer.Option(None, "--version")) -> None:
    """Load and print the content of a prompt."""
    try:
        typer.echo(_service().load_prompt(key, version))
    except PromptError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def diff(
    key: str,
    v1: int,
    v2: int,
    granularity: str = typer.Option("word", "--granularity", "--g"),
) -> None:
    """Show differences between two versions of a prompt."""
    try:
        res = _service().diff_versions(key, v1, v2, granularity=granularity)
        render_diff_to_console(res)
    except PromptError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

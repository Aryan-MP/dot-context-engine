"""dot — the Dot CLI (Typer).

    dot init                 initialize Dot in a project
    dot status               what Dot knows about the current project
    dot ask "question"       query your codebase in natural language
    dot memory list|add|export   browse and manage captured decisions
    dot inject               print assembled context (pipe anywhere)
    dot sync                 force re-index
    dot forget "pattern"     remove memories matching a pattern
    dot dashboard            open the web UI
    dot daemon run|start|stop|install-service
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dot import DEFAULT_PORT, __version__
from dot.config import ProjectConfig, find_project_root

app = typer.Typer(
    name="dot",
    help="Dot — local-first AI context memory daemon.",
    no_args_is_help=True,
)
memory_app = typer.Typer(help="Browse and manage captured decisions.", no_args_is_help=True)
daemon_app = typer.Typer(help="Control the background daemon.", no_args_is_help=True)
app.add_typer(memory_app, name="memory")
app.add_typer(daemon_app, name="daemon")

console = Console()


def _load_config(project: Path | None = None, require_init: bool = True) -> ProjectConfig:
    root = (project or find_project_root())
    if root is None:
        console.print("[red]No project found.[/red] Run inside a project, or `dot init` first.")
        raise typer.Exit(1)
    config = ProjectConfig.load(Path(root))
    if require_init and not config.dot_dir.exists():
        console.print(f"[yellow]Dot isn't initialized in {root}.[/yellow] Run `dot init`.")
        raise typer.Exit(1)
    return config


def _api_base(config: ProjectConfig) -> str:
    return f"http://{config.api_host}:{config.api_port}"


def _try_api(config: ProjectConfig, method: str, path: str, **kwargs):
    """Call the running daemon's API; returns None if it isn't up."""
    import httpx

    try:
        response = httpx.request(method, _api_base(config) + path, timeout=10.0, **kwargs)
        response.raise_for_status()
        return response
    except httpx.ConnectError:
        return None


def _local_daemon(config: ProjectConfig):
    """In-process fallback when the background daemon isn't running."""
    from dot.daemon import Daemon

    return Daemon(config)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


@app.command()
def version() -> None:
    """Print the Dot version."""
    console.print(f"dot {__version__}")


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project directory"),
    claude: bool = typer.Option(True, help="Wire up Claude Code (CLAUDE.md + hook)"),
    git_hook: bool = typer.Option(True, help="Install git post-commit hook"),
    sync_now: bool = typer.Option(True, "--sync/--no-sync", help="Run initial index"),
) -> None:
    """Initialize Dot in a project."""
    root = path.resolve()
    config = ProjectConfig(project_root=str(root))
    config.save()
    console.print(f"[green]✓[/green] initialized .dot/ in [bold]{root}[/bold]")

    if git_hook:
        from dot.integrations.git import GitIntegration

        if GitIntegration(str(root)).install_post_commit_hook():
            console.print("[green]✓[/green] installed git post-commit hook")
    if claude:
        from dot.integrations import claude as claude_integration

        for action in claude_integration.install(config):
            console.print(f"[green]✓[/green] {action}")

    if sync_now:
        console.print("indexing project (first run downloads the embedding model)…")
        daemon = _local_daemon(config)
        result = daemon.full_sync()
        console.print(
            f"[green]✓[/green] indexed {result['files_indexed']} files "
            f"({result['chunks_written']} chunks), "
            f"captured {result['decisions_captured']} decisions from git"
        )
    console.print("\nNext: [bold]dot daemon start[/bold] to keep Dot watching in the background.")


@app.command()
def status() -> None:
    """Show what Dot knows about the current project."""
    config = _load_config()
    response = _try_api(config, "GET", "/status")
    if response is not None:
        data = response.json()
        daemon_state = f"[green]running[/green] ({_api_base(config)})"
    else:
        data = _local_daemon(config).status()
        daemon_state = "[yellow]not running[/yellow] — start with `dot daemon start`"

    table = Table(title=f"Dot · {data.get('project')}", show_header=False)
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_row("daemon", daemon_state)
    table.add_row("project root", str(data.get("project_root")))
    table.add_row("files indexed", str(data.get("files_indexed")))
    table.add_row("chunks", str(data.get("chunks")))
    table.add_row("memories", str(data.get("memories")))
    table.add_row("last indexed", str(data.get("last_indexed") or "never"))
    table.add_row("embeddings", str(data.get("embedding_backend")))
    table.add_row("vector store", str(data.get("vector_backend")))
    if data.get("git_branch"):
        table.add_row("git branch", str(data.get("git_branch")))
    console.print(table)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural-language question about the codebase"),
    fmt: str = typer.Option("markdown", "--fmt", help="markdown | claude | copilot | raw"),
    file: str | None = typer.Option(None, "--file", help="Anchor file for proximity ranking"),
) -> None:
    """Query your codebase in natural language."""
    config = _load_config()
    response = _try_api(
        config, "POST", "/ask",
        json={"question": question, "current_file": file, "fmt": fmt},
    )
    if response is not None:
        output = response.json() if fmt == "raw" else response.text
    else:
        from dot.context.formatter import context_to_dict, format_context

        daemon = _local_daemon(config)
        context = daemon.assembler.assemble(question, current_file=file)
        output = context_to_dict(context) if fmt == "raw" else format_context(context, fmt)
    if isinstance(output, dict):
        console.print_json(json.dumps(output))
    else:
        console.print(output)


@app.command()
def inject(
    query: str = typer.Argument("", help="Optional query to focus the context"),
    file: str | None = typer.Option(None, "--file", help="Current file"),
    fmt: str = typer.Option("claude", "--fmt", help="claude | copilot | markdown | raw"),
    budget: int | None = typer.Option(None, "--budget", help="Token budget"),
    profile: str | None = typer.Option(None, "--profile", help="quick-assist | deep-dive"),
) -> None:
    """Assemble context and print it — pipe into any AI tool."""
    config = _load_config()
    params = {"query": query, "fmt": fmt}
    if file:
        params["file"] = file
    if budget:
        params["token_budget"] = budget
    if profile:
        params["profile"] = profile
    response = _try_api(config, "GET", "/context", params=params)
    if response is not None:
        sys.stdout.write(response.text + "\n")
        return
    from dot.context.formatter import format_context

    daemon = _local_daemon(config)
    context = daemon.assembler.assemble(query, current_file=file, token_budget=budget, profile=profile)
    sys.stdout.write(format_context(context, fmt) + "\n")


@app.command()
def sync(force: bool = typer.Option(False, "--force", help="Re-index unchanged files too")) -> None:
    """Force a re-index of the current project."""
    config = _load_config()
    response = _try_api(config, "POST", "/sync", json={"force": force})
    if response is not None:
        console.print("[green]✓[/green] sync started on the running daemon")
        return
    console.print("daemon not running — syncing in-process…")
    result = _local_daemon(config).full_sync(force=force)
    console.print(
        f"[green]✓[/green] {result['files_indexed']} files indexed, "
        f"{result['chunks_written']} chunks, {result['decisions_captured']} decisions"
    )


@app.command()
def forget(pattern: str = typer.Argument(..., help="Regex/substring to match memories")) -> None:
    """Remove memories matching a pattern."""
    config = _load_config()
    store = _local_daemon(config).store
    matches = [m for m in store.list_memories(limit=10_000) if pattern.lower() in m.content.lower()]
    if not matches:
        console.print("no matching memories")
        return
    for memory in matches[:10]:
        console.print(f"  [dim]{memory.memory_id[:8]}[/dim] {' '.join(memory.content.split())[:90]}")
    if len(matches) > 10:
        console.print(f"  … and {len(matches) - 10} more")
    if not typer.confirm(f"Delete {len(matches)} memories?"):
        raise typer.Abort()
    removed = store.forget_pattern(pattern)
    console.print(f"[green]✓[/green] forgot {removed} memories")


@app.command()
def dashboard() -> None:
    """Open the web dashboard."""
    import webbrowser

    config = _load_config()
    url = f"{_api_base(config)}/ui"
    if _try_api(config, "GET", "/status") is None:
        console.print("[yellow]daemon not running[/yellow] — start it with `dot daemon start`")
        raise typer.Exit(1)
    console.print(f"opening {url}")
    webbrowser.open(url)


# ----------------------------------------------------------------------
# dot memory …
# ----------------------------------------------------------------------
@memory_app.command("list")
def memory_list(
    kind: str | None = typer.Option(None, help="decision | rejected | action_item | note"),
    query: str | None = typer.Option(None, "--query", "-q", help="Semantic search"),
    limit: int = typer.Option(20, help="Max results"),
) -> None:
    """Browse captured memories."""
    config = _load_config()
    store = _local_daemon(config).store
    memories = store.query_memories(query, n=limit) if query else store.list_memories(kind, limit)
    if not memories:
        console.print("no memories yet — they accrue from git commits, comments, and captures")
        return
    table = Table(title="Memories")
    table.add_column("id", style="dim", width=8)
    table.add_column("kind", style="cyan")
    table.add_column("content", max_width=80)
    table.add_column("weight", justify="right")
    table.add_column("source", style="dim")
    for memory in memories:
        table.add_row(
            memory.memory_id[:8], memory.kind,
            " ".join(memory.content.split())[:120],
            f"{memory.weight:.2f}", memory.source,
        )
    console.print(table)


@memory_app.command("add")
def memory_add(
    content: str = typer.Argument(..., help="The decision/note to remember"),
    kind: str = typer.Option("decision", help="decision | rejected | action_item | note"),
    file: str = typer.Option("", "--file", help="Related file path"),
    tag: list[str] = typer.Option([], "--tag", help="Tags (repeatable)"),
) -> None:
    """Capture a decision manually."""
    config = _load_config()
    memory = _local_daemon(config).store.add_memory(
        content=content, kind=kind, source="manual", file_path=file, tags=tag
    )
    console.print(f"[green]✓[/green] captured {memory.memory_id[:8]} ({kind})")


@memory_app.command("export")
def memory_export(
    output: Path = typer.Option(Path("dot-memories.json"), "--output", "-o"),
) -> None:
    """Export all memories as structured JSON."""
    config = _load_config()
    store = _local_daemon(config).store
    payload = {"project": config.project_name, "memories": store.export_memories()}
    output.write_text(json.dumps(payload, indent=2))
    console.print(f"[green]✓[/green] exported {len(payload['memories'])} memories to {output}")


@memory_app.command("delete")
def memory_delete(memory_id: str = typer.Argument(..., help="Memory id (prefix ok)")) -> None:
    """Forget a single memory by id."""
    config = _load_config()
    store = _local_daemon(config).store
    candidates = [m for m in store.list_memories(limit=10_000, include_archived=True)
                  if m.memory_id.startswith(memory_id)]
    if not candidates:
        console.print("[red]no memory with that id[/red]")
        raise typer.Exit(1)
    if len(candidates) > 1:
        console.print(f"[red]{len(candidates)} memories match that prefix; be more specific[/red]")
        raise typer.Exit(1)
    store.delete_memory(candidates[0].memory_id)
    console.print(f"[green]✓[/green] deleted {candidates[0].memory_id[:8]}")


# ----------------------------------------------------------------------
# dot daemon …
# ----------------------------------------------------------------------
@daemon_app.command("run")
def daemon_run(
    project: Path | None = typer.Option(None, "--project", help="Project root"),
    port: int = typer.Option(DEFAULT_PORT, "--port"),
) -> None:
    """Run the daemon in the foreground."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    config = _load_config(project)
    from dot.daemon import Daemon

    Daemon(config).run(port=port)


@daemon_app.command("start")
def daemon_start(
    project: Path | None = typer.Option(None, "--project", help="Project root"),
    port: int = typer.Option(DEFAULT_PORT, "--port"),
) -> None:
    """Start the daemon in the background."""
    from dot.daemon import is_running

    config = _load_config(project)
    if is_running(config):
        console.print("[yellow]daemon already running[/yellow]")
        return
    log_path = config.dot_dir / "daemon.log"
    with open(log_path, "ab") as log_file:
        process = subprocess.Popen(
            [sys.executable, "-m", "dot.cli", "daemon", "run",
             "--project", str(config.project_root), "--port", str(port)],
            stdout=log_file, stderr=log_file,
            start_new_session=True,
        )
    console.print(
        f"[green]✓[/green] daemon started (pid {process.pid}, port {port}) — logs at {log_path}"
    )


@daemon_app.command("stop")
def daemon_stop(project: Path | None = typer.Option(None, "--project")) -> None:
    """Stop the background daemon."""
    import signal as signal_module

    from dot.daemon import read_pid_file, remove_pid_file

    config = _load_config(project)
    info = read_pid_file(config)
    if info is None:
        console.print("daemon not running")
        return
    pid, _port = info
    try:
        os.kill(pid, signal_module.SIGTERM)
        console.print(f"[green]✓[/green] stopped daemon (pid {pid})")
    except ProcessLookupError:
        console.print("daemon process already gone")
    remove_pid_file(config)


@daemon_app.command("install-service")
def daemon_install_service(project: Path | None = typer.Option(None, "--project")) -> None:
    """Install Dot as a user-level system service (launchd/systemd)."""
    from dot.daemon import install_service

    config = _load_config(project)
    try:
        path = install_service(config)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] wrote {path}")
    if sys.platform == "darwin":
        console.print(f"enable with: [bold]launchctl load {path}[/bold]")
    else:
        console.print(
            f"enable with: [bold]systemctl --user enable --now {path.stem}.service[/bold]"
        )


if __name__ == "__main__":
    app()

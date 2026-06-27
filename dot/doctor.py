"""dot doctor — first-run health diagnostics.

Runs a battery of purely-local checks and prints a green/yellow/red report.
Exits 0 when nothing is hard-broken; exits 1 on any hard failure so CI and
scripts can gate on it.

Design notes
------------
- Optional ML deps (sentence-transformers, chromadb, tree-sitter) are a *fail*
  when missing, but the message always notes the graceful-degradation fallback
  and the exact `pip install` extra that fixes it — so a failure is actionable,
  never a dead end. This matches the "exits non-zero when missing ML deps"
  success criterion while still surfacing the fallback.
- The daemon-reachable check is a *warn* (not fail): it is perfectly normal to
  run `dot doctor` before starting the daemon.
- Port-free and daemon-reachable are reconciled: if the daemon answers on the
  port, the port check reports "in use by the Dot daemon" (ok) rather than
  contradicting the reachable check.
- Every check is a pure function returning a `Check`; `run_doctor` composes
  them so tests can call individual checks or the whole battery without
  touching the CLI/Typer exit machinery.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dot import DEFAULT_PORT

Status = Literal["ok", "warn", "fail"]

_OK = "[green]✓[/green]"
_WARN = "[yellow]![/yellow]"
_FAIL = "[red]✗[/red]"
_ICON = {"ok": _OK, "warn": _WARN, "fail": _FAIL}


@dataclass
class Check:
    """A single doctor check result."""

    name: str
    status: Status
    message: str

    @property
    def passed(self) -> bool:
        """True unless this is a hard failure."""
        return self.status != "fail"


def _check_python() -> Check:
    v = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    # Intentional runtime check: doctor must surface a clear diagnostic even
    # when invoked against a mismatched interpreter (e.g. `python -m dot.cli`
    # under an older Python), so we don't rely solely on requires-python.
    if sys.version_info >= (3, 11):  # noqa: UP036
        return Check("Python", "ok", f"{v} (>= 3.11)")
    return Check("Python", "fail", f"{v} — Dot requires Python 3.11 or newer")


def _check_import(
    label: str, module: str, install_extra: str, fallback: str
) -> Check:
    """Try to import `module`; on failure, report the fallback + install hint."""
    try:
        __import__(module)
        return Check(label, "ok", "importable")
    except ImportError:
        return Check(
            label,
            "fail",
            f"not importable — Dot will fall back to {fallback}. "
            f"Install with: pip install 'dot-context{install_extra}'",
        )


def check_sentence_transformers() -> Check:
    return _check_import(
        "sentence-transformers",
        "sentence_transformers",
        "[ml]",
        "a deterministic hashing embedder (lower retrieval quality)",
    )


def check_chromadb() -> Check:
    return _check_import(
        "chromadb",
        "chromadb",
        "[ml]",
        "SQLite brute-force vector search (slower on large indexes)",
    )


def check_tree_sitter() -> Check:
    try:
        __import__("tree_sitter")
        __import__("tree_sitter_language_pack")
        return Check("tree-sitter", "ok", "importable (multi-language AST parsing)")
    except ImportError:
        return Check(
            "tree-sitter",
            "fail",
            "not importable — Dot will fall back to ast/regex parsing for "
            "non-Python files (no docstrings, estimated block ends). "
            "Install with: pip install 'dot-context[treesitter]'",
        )


def check_port_free(port: int = DEFAULT_PORT, daemon_ok: bool = False) -> Check:
    """Is `port` available — or already held by the Dot daemon?"""
    if daemon_ok:
        return Check(f"port {port}", "ok", "in use by the Dot daemon")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
        return Check(f"port {port}", "ok", "free")
    except OSError:
        return Check(
            f"port {port}",
            "fail",
            "in use by another process — the daemon will auto-bump to the "
            "next free port, or set `api_port` in .dot/config.json",
        )


def check_git_repo(root: Path | None) -> Check:
    if root is None:
        return Check("git repo", "warn", "no project root — run inside a project to check")
    if (root / ".git").exists():
        return Check("git repo", "ok", f"detected in {root}")
    # worktrees / submodule gitdir pointers resolve through git itself
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Check("git repo", "ok", f"detected in {root}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return Check(
        "git repo",
        "fail",
        f"not a git repository ({root}) — decision mining from commits and "
        "git hooks are disabled. Run `git init` to enable.",
    )


def check_dot_writable(root: Path | None) -> Check:
    if root is None:
        return Check(".dot/ writable", "warn", "no project root — run inside a project to check")
    dot_dir = root / ".dot"
    try:
        dot_dir.mkdir(parents=True, exist_ok=True)
        probe = dot_dir / ".doctor-probe"
        probe.write_text("ok")
        probe.unlink()
        return Check(".dot/ writable", "ok", str(dot_dir))
    except OSError as exc:
        return Check(
            ".dot/ writable",
            "fail",
            f"cannot write to {dot_dir} ({exc}) — check directory permissions",
        )


def check_daemon_reachable(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> Check:
    """Probe the daemon's /status endpoint. Down is a *warning*, not a failure."""
    import httpx

    try:
        response = httpx.get(f"http://{host}:{port}/status", timeout=2.0)
        if response.status_code == 200:
            return Check("daemon", "ok", f"reachable at {host}:{port}")
        return Check(
            "daemon", "warn", f"responded HTTP {response.status_code} at {host}:{port}"
        )
    except httpx.ConnectError:
        return Check(
            "daemon",
            "warn",
            f"not running at {host}:{port} — start with `dot daemon start`",
        )
    except Exception as exc:  # timeouts, etc.
        return Check("daemon", "warn", f"could not reach {host}:{port} ({exc})")


def run_doctor(
    project_root: Path | None = None, port: int | None = None
) -> list[Check]:
    """Run the full check battery and return results in display order."""
    p = port if port is not None else DEFAULT_PORT
    daemon = check_daemon_reachable(port=p)
    return [
        _check_python(),
        check_sentence_transformers(),
        check_chromadb(),
        check_tree_sitter(),
        check_port_free(p, daemon_ok=(daemon.status == "ok")),
        check_git_repo(project_root),
        check_dot_writable(project_root),
        daemon,
    ]


def render(checks: list[Check], console) -> tuple[int, int, int]:
    """Print checks to `console`; return (ok, warn, fail) counts."""
    from rich.markup import escape

    counts = {"ok": 0, "warn": 0, "fail": 0}
    for check in checks:
        counts[check.status] += 1
        # Escape the name/message: install hints contain literal `[ml]`/`[treesitter]`
        # which rich would otherwise parse as style tags and strip from output.
        console.print(
            f"{_ICON[check.status]} {escape(check.name)} — {escape(check.message)}"
        )
    return counts["ok"], counts["warn"], counts["fail"]

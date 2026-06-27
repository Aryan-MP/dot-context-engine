"""Tests for `dot doctor` — first-run health diagnostics.

Covers:
  - Individual check functions (Python, ML deps with real fallback path,
    port free/busy/daemon-held, git repo, .dot/ writable, daemon down).
  - run_doctor() composition: healthy path (exit 0), missing-ML-deps failure,
    unwritable .dot/ failure.
  - CLI exit codes via Typer's CliRunner (exit 0 healthy, exit 1 on failure).

The ML-dep fallback path is exercised for real: we poison sys.modules with
None for the target module so __import__ raises ImportError, which makes the
check run its genuine fallback branch and emit the install hint. This is
deterministic regardless of whether the deps are actually installed in the
test environment.
"""

from __future__ import annotations

import os
import socket
import sys

import pytest
from typer.testing import CliRunner

from dot.cli import app
from dot.doctor import (
    Check,
    _check_python,
    check_chromadb,
    check_daemon_reachable,
    check_dot_writable,
    check_git_repo,
    check_port_free,
    check_sentence_transformers,
    check_tree_sitter,
    render,
    run_doctor,
)

runner = CliRunner()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _poison_modules(monkeypatch, *names: str) -> None:
    """Make `__import__(name)` raise ImportError by setting sys.modules to None."""
    for name in names:
        monkeypatch.setitem(sys.modules, name, None)


def _ok(name: str = "stub") -> Check:
    return Check(name, "ok", "stubbed ok")


def _free_port() -> int:
    """Grab an ephemeral port the OS will hand out, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
_IS_WINDOWS = os.name == "nt"
skip_if_root_or_windows = pytest.mark.skipif(
    _IS_ROOT or _IS_WINDOWS,
    reason="read-only-directory semantics require non-root POSIX",
)


# --------------------------------------------------------------------------- #
# Individual check functions
# --------------------------------------------------------------------------- #
def test_python_check_ok_on_modern_interpreter():
    check = _check_python()
    assert check.status == "ok"
    assert ">= 3.11" in check.message


def test_python_check_fails_on_old_interpreter(monkeypatch):
    from collections import namedtuple

    # namedtuple behaves like a tuple (supports >= (3, 11)) AND exposes
    # .major/.minor/.micro attributes that _check_python reads.
    VI = namedtuple("VI", "major minor micro")
    monkeypatch.setattr(sys, "version_info", VI(3, 10, 0), raising=False)
    check = _check_python()
    assert check.status == "fail"
    assert "3.11 or newer" in check.message


def test_check_sentence_transformers_ok_when_importable(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", type(sys)("sentence_transformers"))
    check = check_sentence_transformers()
    assert check.status == "ok"
    assert check.message == "importable"


def test_check_sentence_transformers_fallback_when_missing(monkeypatch):
    _poison_modules(monkeypatch, "sentence_transformers")
    check = check_sentence_transformers()
    assert check.status == "fail"
    assert "not importable" in check.message
    assert "fall back to" in check.message  # notes the fallback
    assert "dot-context[ml]" in check.message  # actionable install hint


def test_check_chromadb_fallback_when_missing(monkeypatch):
    _poison_modules(monkeypatch, "chromadb")
    check = check_chromadb()
    assert check.status == "fail"
    assert "fall back to" in check.message
    assert "dot-context[ml]" in check.message


def test_check_tree_sitter_fallback_when_missing(monkeypatch):
    _poison_modules(monkeypatch, "tree_sitter", "tree_sitter_language_pack")
    check = check_tree_sitter()
    assert check.status == "fail"
    assert "fall back to" in check.message
    assert "dot-context[treesitter]" in check.message


def test_check_port_free_when_available():
    port = _free_port()
    check = check_port_free(port)
    assert check.status == "ok"
    assert "free" in check.message


def test_check_port_free_reports_daemon_held():
    port = _free_port()
    check = check_port_free(port, daemon_ok=True)
    assert check.status == "ok"
    assert "in use by the Dot daemon" in check.message


def test_check_port_free_fails_when_busy():
    port = _free_port()
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", port))
    holder.listen(1)
    try:
        check = check_port_free(port)
        assert check.status == "fail"
        assert "in use" in check.message
    finally:
        holder.close()


def test_check_git_repo_ok_when_dot_git_present(tmp_path):
    (tmp_path / ".git").mkdir()
    check = check_git_repo(tmp_path)
    assert check.status == "ok"
    assert "detected" in check.message


def test_check_git_repo_fails_when_not_a_repo(tmp_path):
    check = check_git_repo(tmp_path)
    assert check.status == "fail"
    assert "not a git repository" in check.message


def test_check_git_repo_warns_when_no_root():
    check = check_git_repo(None)
    assert check.status == "warn"
    assert "no project root" in check.message


def test_check_dot_writable_ok(tmp_path):
    check = check_dot_writable(tmp_path)
    assert check.status == "ok"
    # probe file must be cleaned up
    assert not (tmp_path / ".dot" / ".doctor-probe").exists()


@skip_if_root_or_windows
def test_check_dot_writable_fails_when_readonly(tmp_path):
    dot_dir = tmp_path / ".dot"
    dot_dir.mkdir()
    os.chmod(dot_dir, 0o444)
    try:
        check = check_dot_writable(tmp_path)
        assert check.status == "fail"
        assert "cannot write" in check.message
    finally:
        os.chmod(dot_dir, 0o755)  # restore so pytest can clean up


def test_check_dot_writable_fails_when_blocked_by_file(tmp_path):
    # Cross-platform deterministic failure: .dot exists as a regular file,
    # so mkdir(exist_ok=True) raises FileExistsError.
    (tmp_path / ".dot").write_text("blocker")
    check = check_dot_writable(tmp_path)
    assert check.status == "fail"
    assert "cannot write" in check.message


def test_check_daemon_reachable_warns_when_down():
    # Port 1 is privileged and nothing listens there → ConnectError → warn.
    check = check_daemon_reachable(port=1)
    assert check.status == "warn"
    assert "not running" in check.message


# --------------------------------------------------------------------------- #
# run_doctor() composition
# --------------------------------------------------------------------------- #
def test_run_doctor_healthy_path(monkeypatch, tmp_path):
    """All checks pass → no failures, exit would be 0."""
    (tmp_path / ".git").mkdir()  # git repo
    # Stub the env-dependent checks to ok so the composition is fully healthy.
    monkeypatch.setattr("dot.doctor.check_sentence_transformers", lambda: _ok("sentence-transformers"))
    monkeypatch.setattr("dot.doctor.check_chromadb", lambda: _ok("chromadb"))
    monkeypatch.setattr("dot.doctor.check_tree_sitter", lambda: _ok("tree-sitter"))
    monkeypatch.setattr("dot.doctor.check_daemon_reachable", lambda **k: _ok("daemon"))

    checks = run_doctor(project_root=tmp_path, port=_free_port())

    assert all(c.passed for c in checks), [c for c in checks if not c.passed]
    fails = [c for c in checks if c.status == "fail"]
    assert fails == []


def test_run_doctor_missing_ml_deps_failure(monkeypatch, tmp_path):
    """Missing ML deps surface as failures that mention the fallback path."""
    (tmp_path / ".git").mkdir()
    _poison_modules(monkeypatch, "sentence_transformers", "chromadb", "tree_sitter", "tree_sitter_language_pack")
    monkeypatch.setattr("dot.doctor.check_daemon_reachable", lambda **k: _ok("daemon"))

    checks = run_doctor(project_root=tmp_path, port=_free_port())

    fails = [c for c in checks if c.status == "fail"]
    assert len(fails) == 3
    names = {c.name for c in fails}
    assert names == {"sentence-transformers", "chromadb", "tree-sitter"}
    for c in fails:
        assert "fall back to" in c.message
    # python / port / git / .dot / daemon must all be ok or warn (no extra fails)
    non_ml = [c for c in checks if c.name not in names]
    assert all(c.status != "fail" for c in non_ml)


def test_run_doctor_unwritable_dot_failure(monkeypatch, tmp_path):
    """Unwritable .dot/ surfaces as a single, specific failure."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".dot").write_text("blocker")  # file blocks the dir
    monkeypatch.setattr("dot.doctor.check_sentence_transformers", lambda: _ok())
    monkeypatch.setattr("dot.doctor.check_chromadb", lambda: _ok())
    monkeypatch.setattr("dot.doctor.check_tree_sitter", lambda: _ok())
    monkeypatch.setattr("dot.doctor.check_daemon_reachable", lambda **k: _ok("daemon"))

    checks = run_doctor(project_root=tmp_path, port=_free_port())

    dot_check = next(c for c in checks if c.name == ".dot/ writable")
    assert dot_check.status == "fail"
    assert "cannot write" in dot_check.message
    # only the .dot check should fail
    fails = [c for c in checks if c.status == "fail"]
    assert len(fails) == 1


# --------------------------------------------------------------------------- #
# render()
# --------------------------------------------------------------------------- #
def test_render_counts_and_escapes_markup(monkeypatch):
    """render() must escape literal [ml] tags so install hints aren't stripped."""
    from rich.console import Console

    checks = [
        Check("Python", "ok", "3.14"),
        Check("sentence-transformers", "fail",
              "missing — Install with: pip install 'dot-context[ml]'"),
    ]
    captured: list[str] = []
    console = Console(file=_Capture(captured), force_terminal=False, color_system=None, width=200)

    ok, warns, fails = render(checks, console)
    output = "".join(captured)

    assert (ok, warns, fails) == (1, 0, 1)
    # The literal [ml] must survive rich markup parsing
    assert "dot-context[ml]" in output


class _Capture:
    """Minimal file-like object that collects rich-rendered text."""

    def __init__(self, sink: list[str]):
        self.sink = sink

    def write(self, text: str) -> int:
        self.sink.append(text)
        return len(text)

    def flush(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# CLI exit codes
# --------------------------------------------------------------------------- #
def test_doctor_cli_exits_0_when_healthy(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".dot").mkdir()
    monkeypatch.setattr("dot.doctor.check_sentence_transformers", lambda: _ok("sentence-transformers"))
    monkeypatch.setattr("dot.doctor.check_chromadb", lambda: _ok("chromadb"))
    monkeypatch.setattr("dot.doctor.check_tree_sitter", lambda: _ok("tree-sitter"))
    monkeypatch.setattr("dot.doctor.check_daemon_reachable", lambda **k: _ok("daemon"))

    result = runner.invoke(app, ["doctor", "--project", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "0 failures" in result.output


def test_doctor_cli_exits_1_when_ml_deps_missing(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".dot").mkdir()
    _poison_modules(monkeypatch, "sentence_transformers", "chromadb", "tree_sitter", "tree_sitter_language_pack")
    monkeypatch.setattr("dot.doctor.check_daemon_reachable", lambda **k: _ok("daemon"))

    result = runner.invoke(app, ["doctor", "--project", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "failures" in result.output
    assert "sentence-transformers" in result.output
    # install hint survives markup escaping through the CLI too
    assert "dot-context[ml]" in result.output


def test_doctor_cli_exits_1_when_dot_unwritable(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".dot").write_text("blocker")
    monkeypatch.setattr("dot.doctor.check_sentence_transformers", lambda: _ok())
    monkeypatch.setattr("dot.doctor.check_chromadb", lambda: _ok())
    monkeypatch.setattr("dot.doctor.check_tree_sitter", lambda: _ok())
    monkeypatch.setattr("dot.doctor.check_daemon_reachable", lambda **k: _ok("daemon"))

    result = runner.invoke(app, ["doctor", "--project", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "cannot write" in result.output
    assert ".dot/ writable" in result.output

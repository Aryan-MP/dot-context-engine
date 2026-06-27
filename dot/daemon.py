"""The Dot daemon.

Orchestrates the pipeline: watcher → parser → chunker → embedder → store.
Also runs periodic jobs (git decision mining, memory decay pruning,
Copilot instructions refresh) and serves the REST API on localhost:7337.

Run in the foreground with ``dot daemon run``; ``dot init`` can install it
as a system service (launchd on macOS, systemd on Linux).
"""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from dot import DEFAULT_HOST, DEFAULT_PORT
from dot.config import SHARED_MEMORIES_FILE, ProjectConfig, dot_home
from dot.context.assembler import ContextAssembler
from dot.conversations import ClaudeCodeSource, ConversationIngester
from dot.conversations.watcher import ConversationWatcher
from dot.indexer.chunker import chunk_file
from dot.indexer.parser import CodeParser
from dot.indexer.watcher import ProjectWatcher, walk_project
from dot.integrations.copilot import write_instructions_file
from dot.integrations.git import GitIntegration
from dot.memory.decisions import DecisionService
from dot.memory.shared import import_shared
from dot.memory.store import Store

logger = logging.getLogger(__name__)


class Daemon:
    """One daemon process serves one project (the common local-first case)."""

    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.store = Store(config)
        self.parser = CodeParser()
        self.assembler = ContextAssembler(self.store, config)
        self.decisions = DecisionService(self.store)
        self.git = GitIntegration(config.project_root)
        self.watcher = ProjectWatcher(config, self._on_change)
        # Conversation capture is opt-in; the ingester is built lazily only
        # when the feature is enabled so a plain daemon start costs nothing
        # when ~/.claude is absent or the user hasn't opted in.
        self._conversations: ConversationIngester | None = None
        self._conversation_watcher: ConversationWatcher | None = None
        if self.conversations_enabled:
            self._conversation_watcher = ConversationWatcher(
                config, ClaudeCodeSource(), self.scan_conversations
            )
        self.started_at = datetime.now(UTC)
        self._scheduler = None
        self._index_lock = threading.Lock()
        self._stats = {"files_indexed": 0, "chunks_indexed": 0, "errors": 0}

    # ------------------------------------------------------------------
    # Indexing pipeline
    # ------------------------------------------------------------------
    def index_file(self, path: Path, force: bool = False) -> int:
        """Parse → chunk → embed → store one file. Returns chunks written."""
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0
        content_hash = hashlib.sha256(source.encode()).hexdigest()
        file_key = self._relative(path)
        if not force and self.store.file_hash(file_key) == content_hash:
            return 0  # unchanged
        chunks = chunk_file(path, source, self.parser)
        for chunk in chunks:
            chunk.file_path = file_key
        with self._index_lock:
            written = self.store.upsert_chunks(chunks, content_hash)
        self._stats["files_indexed"] += 1
        self._stats["chunks_indexed"] += written
        return written

    def _relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(Path(self.config.project_root).resolve()))
        except ValueError:
            return str(path)

    def _on_change(self, event_type: str, path: Path) -> None:
        if path.name == SHARED_MEMORIES_FILE:
            # A teammate's shared memories arrived (e.g. via git pull).
            if event_type != "deleted":
                imported = import_shared(self.store, self.config)
                if imported:
                    logger.info("imported %d shared memories", imported)
            return
        if event_type == "deleted":
            self.store.delete_file(self._relative(path))
            logger.info("removed index for %s", path)
        else:
            written = self.index_file(path)
            if written:
                logger.info("indexed %s (%d chunks)", path, written)

    def full_sync(self, force: bool = False) -> dict:
        """Re-index the whole project, re-mine git, import shared memories."""
        files = walk_project(self.config)
        chunks_written = 0
        files_touched = 0
        for path in files:
            try:
                written = self.index_file(path, force=force)
            except Exception:
                logger.exception("failed indexing %s", path)
                self._stats["errors"] += 1
                continue
            if written:
                files_touched += 1
                chunks_written += written
        decisions = self.decisions.mine_git()
        shared = import_shared(self.store, self.config)
        return {
            "files_scanned": len(files),
            "files_indexed": files_touched,
            "chunks_written": chunks_written,
            "decisions_captured": decisions,
            "shared_imported": shared,
            "git_available": self.git.available,
        }

    # ------------------------------------------------------------------
    # Conversation capture (opt-in)
    # ------------------------------------------------------------------
    @property
    def conversations_enabled(self) -> bool:
        return bool(self.config.capture_conversations)

    def conversations(self) -> ConversationIngester | None:
        """The conversation ingester, lazily built when capture is enabled."""
        if not self.conversations_enabled:
            return None
        if self._conversations is None:
            self._conversations = ConversationIngester(
                self.store, source=ClaudeCodeSource()
            )
        return self._conversations

    def scan_conversations(self) -> dict:
        """Run one incremental conversation scan (daemon/CLI/API entrypoint)."""
        ingester = self.conversations()
        if ingester is None:
            return {
                "enabled": False,
                "transcripts_scanned": 0,
                "decisions_captured": 0,
                "errors": 0,
            }
        result = ingester.scan(self.config.project_root, incremental=True)
        return {
            "enabled": True,
            "transcripts_scanned": result.transcripts_scanned,
            "turns_read": result.turns_read,
            "decisions_captured": result.decisions_captured,
            "newly_captured": result.newly_captured,
            "errors": result.errors,
        }

    # ------------------------------------------------------------------
    # Background jobs
    # ------------------------------------------------------------------
    def _start_scheduler(self) -> None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            logger.warning("APScheduler not installed; periodic jobs disabled")
            return
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(self.decisions.mine_git, "interval", minutes=15, id="mine-git")
        scheduler.add_job(self.store.prune_decayed, "interval", hours=6, id="prune-memories")
        if "copilot" in self.config.integrations:
            scheduler.add_job(
                lambda: write_instructions_file(self.store), "interval", hours=1,
                id="copilot-instructions",
            )
        if self.conversations_enabled:
            # ~10 min balances freshness against cost; the ingester is
            # incremental (byte offsets) so each tick only reads new appends.
            scheduler.add_job(
                self.scan_conversations, "interval", minutes=10, id="scan-conversations"
            )
        scheduler.start()
        self._scheduler = scheduler

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def status(self) -> dict:
        stats = self.store.stats()
        stats.update(
            {
                "daemon_started_at": self.started_at.isoformat(),
                "uptime_seconds": int((datetime.now(UTC) - self.started_at).total_seconds()),
                "git_branch": self.git.current_branch(),
                "session_stats": dict(self._stats),
            }
        )
        return stats

    def run(self, host: str | None = None, port: int | None = None) -> None:
        """Foreground entrypoint: initial sync, watcher, scheduler, API."""
        import uvicorn

        from dot.api import create_app

        host = host or self.config.api_host or DEFAULT_HOST
        port = resolve_port(self.config, host, port or self.config.api_port or DEFAULT_PORT)

        write_pid_file(self.config, os.getpid(), port)
        logger.info("dot daemon starting for %s", self.config.project_root)

        def _initial_sync() -> None:
            self.full_sync()
            if self.conversations_enabled:
                try:
                    self.scan_conversations()
                except Exception:  # noqa: BLE001 -- startup must not abort on transcript errors
                    logger.exception("initial conversation scan failed")

        sync_thread = threading.Thread(target=_initial_sync, daemon=True, name="dot-sync")
        sync_thread.start()
        self.watcher.start()
        if self._conversation_watcher:
            self._conversation_watcher.start()
        self._start_scheduler()

        def shutdown(*_args) -> None:
            logger.info("shutting down")
            self.watcher.stop()
            if self._conversation_watcher:
                self._conversation_watcher.stop()
            if self._scheduler:
                self._scheduler.shutdown(wait=False)
            remove_pid_file(self.config)
            sys.exit(0)

        signal.signal(signal.SIGTERM, shutdown)
        try:
            uvicorn.run(create_app(self), host=host, port=port, log_level="warning")
        finally:
            self.watcher.stop()
            if self._conversation_watcher:
                self._conversation_watcher.stop()
            if self._scheduler:
                self._scheduler.shutdown(wait=False)
            remove_pid_file(self.config)


# ----------------------------------------------------------------------
# Port resolution — every project gets its own daemon; when the preferred
# port is taken (another project's daemon), walk up to the next free one
# and persist it so the CLI, hooks, and integrations all agree.
# ----------------------------------------------------------------------
def _port_free(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def resolve_port(config: ProjectConfig, host: str, preferred: int, attempts: int = 100) -> int:
    for offset in range(attempts):
        candidate = preferred + offset
        if _port_free(host, candidate):
            if candidate != config.api_port:
                config.api_port = candidate
                config.save()
                logger.info("port %d busy; using %d (saved to config)", preferred, candidate)
            return candidate
    raise RuntimeError(f"no free port in {preferred}-{preferred + attempts}")


# ----------------------------------------------------------------------
# PID-file management (used by `dot daemon start/stop/status`)
# ----------------------------------------------------------------------
def _pid_path(config: ProjectConfig) -> Path:
    digest = hashlib.sha256(config.project_root.encode()).hexdigest()[:12]
    return dot_home() / f"daemon-{digest}.pid"


def write_pid_file(config: ProjectConfig, pid: int, port: int) -> None:
    _pid_path(config).write_text(f"{pid}\n{port}\n{config.project_root}\n")


def read_pid_file(config: ProjectConfig) -> tuple[int, int] | None:
    path = _pid_path(config)
    if not path.exists():
        return None
    try:
        pid_line, port_line, *_ = path.read_text().splitlines()
        return int(pid_line), int(port_line)
    except (ValueError, IndexError):
        return None


def remove_pid_file(config: ProjectConfig) -> None:
    _pid_path(config).unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    """Whether a process with this PID exists, cross-platform.

    ``os.kill(pid, 0)`` is POSIX-only; signal 0 is invalid on Windows, so we
    branch on platform to avoid crashing the whole daemon lifecycle there.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def is_running(config: ProjectConfig) -> bool:
    info = read_pid_file(config)
    if info is None:
        return False
    pid, _port = info
    if _pid_alive(pid):
        return True
    remove_pid_file(config)
    return False


# ----------------------------------------------------------------------
# System service installation
# ----------------------------------------------------------------------
SYSTEMD_UNIT = """[Unit]
Description=Dot context memory daemon ({project})
After=network.target

[Service]
ExecStart={dot_bin} daemon run --project {project_root}
Restart=on-failure
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""

LAUNCHD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>dev.dot.daemon.{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{dot_bin}</string>
    <string>daemon</string>
    <string>run</string>
    <string>--project</string>
    <string>{project_root}</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
"""


def install_service(config: ProjectConfig) -> Path:
    """Write a user-level service definition; returns the path written.

    The caller (CLI) prints the enable command — we don't run systemctl or
    launchctl ourselves so this stays predictable and non-destructive.
    """
    import shutil

    dot_bin = shutil.which("dot") or f"{sys.executable} -m dot.cli"
    label = hashlib.sha256(config.project_root.encode()).hexdigest()[:8]

    if sys.platform == "darwin":
        path = Path.home() / "Library" / "LaunchAgents" / f"dev.dot.daemon.{label}.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            LAUNCHD_PLIST.format(dot_bin=dot_bin, project_root=config.project_root, label=label)
        )
    elif sys.platform.startswith("linux"):
        path = Path.home() / ".config" / "systemd" / "user" / f"dot-{label}.service"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            SYSTEMD_UNIT.format(
                dot_bin=dot_bin, project=config.project_name, project_root=config.project_root
            )
        )
    else:
        raise RuntimeError(
            "automatic service install supports macOS (launchd) and Linux (systemd); "
            "on Windows, run `dot daemon run` via Task Scheduler or NSSM"
        )
    return path

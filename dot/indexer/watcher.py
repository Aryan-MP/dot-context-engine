"""Filesystem watcher.

Uses watchdog to observe a project tree and emit debounced change events.
Rapid bursts of writes to the same file (editors, formatters, build tools)
collapse into a single event so the indexing pipeline isn't flooded.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from dot.config import SHARED_MEMORIES_FILE, ProjectConfig

logger = logging.getLogger(__name__)

# (event_type, path) where event_type is "changed" or "deleted"
ChangeCallback = Callable[[str, Path], None]


@dataclass
class _PendingChange:
    event_type: str
    path: Path
    timestamp: float = field(default_factory=time.monotonic)


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, watcher: ProjectWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        self._enqueue("changed", event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._enqueue("changed", event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._enqueue("deleted", event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._enqueue("deleted", event)
        dest = getattr(event, "dest_path", None)
        if dest:
            self._watcher.enqueue("changed", Path(str(dest)))

    def _enqueue(self, event_type: str, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._watcher.enqueue(event_type, Path(str(event.src_path)))


class ProjectWatcher:
    """Watches a project tree and invokes a callback with debounced changes."""

    def __init__(
        self,
        config: ProjectConfig,
        on_change: ChangeCallback,
        debounce_seconds: float = 1.5,
    ) -> None:
        self.config = config
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self._pending: dict[Path, _PendingChange] = {}
        self._lock = threading.Lock()
        self._observer: Observer | None = None
        self._flusher: threading.Thread | None = None
        self._stop = threading.Event()

    def is_relevant(self, path: Path) -> bool:
        # The shared-memories file is not indexed as code, but changes to it
        # (e.g. after `git pull`) must reach the daemon so it can import them.
        if path.name != SHARED_MEMORIES_FILE and path.suffix.lower() not in self.config.indexable_extensions:
            return False
        try:
            relative = path.resolve().relative_to(Path(self.config.project_root).resolve())
        except ValueError:
            return False
        return not any(part in self.config.ignored_dirs for part in relative.parts)

    def enqueue(self, event_type: str, path: Path) -> None:
        if not self.is_relevant(path):
            return
        with self._lock:
            self._pending[path] = _PendingChange(event_type, path)

    def _flush_loop(self) -> None:
        while not self._stop.wait(0.5):
            self._flush()
        self._flush()

    def _flush(self) -> None:
        now = time.monotonic()
        ready: list[_PendingChange] = []
        with self._lock:
            for path in list(self._pending):
                change = self._pending[path]
                if now - change.timestamp >= self.debounce_seconds:
                    ready.append(self._pending.pop(path))
        for change in ready:
            try:
                self.on_change(change.event_type, change.path)
            except Exception:
                logger.exception("change callback failed for %s", change.path)

    def start(self) -> None:
        self._stop.clear()
        self._observer = Observer()
        self._observer.schedule(
            _DebouncedHandler(self), self.config.project_root, recursive=True
        )
        self._observer.start()
        self._flusher = threading.Thread(target=self._flush_loop, daemon=True, name="dot-flush")
        self._flusher.start()
        logger.info("watching %s", self.config.project_root)

    def stop(self) -> None:
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._flusher:
            self._flusher.join(timeout=5)
            self._flusher = None


def walk_project(config: ProjectConfig) -> list[Path]:
    """All indexable files in the project, respecting ignore rules."""
    root = Path(config.project_root)
    ignored = config.ignored_dirs
    extensions = config.indexable_extensions
    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if path.name == SHARED_MEMORIES_FILE:
            continue  # imported as memories, not indexed as code
        relative = path.relative_to(root)
        if any(part in ignored for part in relative.parts):
            continue
        results.append(path)
    return results

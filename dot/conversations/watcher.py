"""Filesystem watcher for conversation transcripts.

Unlike :class:`dot.indexer.watcher.ProjectWatcher`, transcripts do **not**
live under the project root -- they live under ``~/.claude/projects/...``
(or ``$CLAUDE_CONFIG_DIR``), outside the project tree. So a separate,
lighter watcher observes that directory and triggers an incremental scan
when a ``.jsonl`` transcript is created or appended.

Project filtering is delegated to the ingester (which reads the per-line
``cwd`` field), so this watcher fires on *any* transcript change in the
resolved directory and lets the idempotent, cwd-filtered scan decide what
actually belongs to this project.

The watcher degrades to a silent no-op when:

- capture is disabled in config (the daemon never constructs it), or
- the transcript directory doesn't exist (Claude Code isn't installed /
  hasn't been used here yet).

A periodic scheduler job (:meth:`dot.daemon.Daemon.scan_conversations`)
runs as a backstop so a missed watcher event (e.g. the daemon was down
when a session was written) still gets picked up on the next tick.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from dot.conversations.source import ConversationSource

logger = logging.getLogger(__name__)

ChangeCallback = Callable[[], None]


class _TranscriptHandler(FileSystemEventHandler):
    """Forward ``.jsonl`` changes, debounced by the owning watcher."""

    def __init__(self, watcher: ConversationWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        self._watcher._enqueue(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._watcher._enqueue(event)


class ConversationWatcher:
    """Watches a conversation transcript directory and fires a debounced scan.

    The callback receives no arguments -- it typically calls
    :meth:`Daemon.scan_conversations`, which does the incremental read and
    cwd-based filtering itself. Debouncing collapses a burst of appends
    (Claude Code flushes frequently) into one scan.
    """

    def __init__(
        self,
        config,
        source: ConversationSource,
        on_change: ChangeCallback,
        debounce_seconds: float = 2.0,
    ) -> None:
        self.config = config
        self.source = source
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self._last_fire = 0.0
        self._pending = threading.Event()
        self._observer: Observer | None = None
        self._flusher: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def watch_dir(self) -> Path | None:
        """The transcript directory this watcher observes, or None."""
        return self.source.transcript_dir(self.config.project_root)

    def _enqueue(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.suffix.lower() != ".jsonl":
            return
        self._last_fire = time.monotonic()
        self._pending.set()

    def _flush_loop(self) -> None:
        while not self._stop.wait(0.5):
            if self._pending.is_set() and self._debounced():
                self._pending.clear()
                try:
                    self.on_change()
                except Exception:  # noqa: BLE001 -- a scan failure must not kill the watcher
                    logger.exception("conversation scan callback failed")

    def _debounced(self) -> bool:
        return (time.monotonic() - self._last_fire) >= self.debounce_seconds

    def start(self) -> None:
        directory = self.watch_dir
        if directory is None:
            logger.info("conversation capture: no transcript dir resolved, watcher idle")
            return
        if not directory.is_dir():
            logger.info("conversation capture: transcript dir %s absent, watcher idle", directory)
            return
        self._stop.clear()
        self._observer = Observer()
        self._observer.schedule(_TranscriptHandler(self), str(directory), recursive=True)
        try:
            self._observer.start()
        except OSError as exc:
            # Some platforms refuse to watch certain paths; the scheduler
            # backstop still catches new transcripts every ~10 min.
            logger.warning("cannot watch transcript dir %s: %s", directory, exc)
            self._observer = None
            return
        self._flusher = threading.Thread(
            target=self._flush_loop, daemon=True, name="dot-conv-flush"
        )
        self._flusher.start()
        logger.info("watching conversation transcripts in %s", directory)

    def stop(self) -> None:
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._flusher:
            self._flusher.join(timeout=5)
            self._flusher = None

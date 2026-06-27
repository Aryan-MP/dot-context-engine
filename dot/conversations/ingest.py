"""Wiring: transcript turns -> Dot's memory, via the existing decision pipeline.

This layer is intentionally thin. It does *not* fork the decision pipeline:
each decision-bearing turn is converted into a :class:`CapturedDecision` and
handed to :meth:`DecisionService.capture`, which is the same code path
``capture_from_conversation`` and git mining use. That reuse is what
guarantees idempotency (memory id = ``sha256(source::content)``) and a
single, consistent source-formatting convention.

A scan is:

1. resolve a :class:`ConversationSource` (Claude Code by default),
2. for each transcript file, read its turns (incrementally, if the source
   supports it),
3. split each turn's text into paragraph blocks and run
   :func:`parse_decision` over each,
4. capture the decisions that match, tagging them with the session id,
5. report a :class:`ScanResult`.

Returns counts, never raises on a per-file failure -- a broken transcript is
logged and skipped, so one bad file can't poison a scan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from dot.conversations.claude_code import ClaudeCodeSource, IncrementalReader
from dot.conversations.source import ConversationSource, ConversationTurn, TranscriptFile
from dot.memory.decisions import CapturedDecision, DecisionService, parse_decision
from dot.memory.store import Memory, Store

logger = logging.getLogger(__name__)

# Decision patterns match short rationales, so split a long turn into
# paragraph blocks and evaluate each independently -- the same boundary
# capture_from_conversation uses, applied per turn.
_BLOCK_SPLIT = "\n\n"

# Persisted per-file byte offsets live in the project's .dot/ directory so a
# background scan resumes where the last one left off instead of re-reading
# every transcript from the top every time.
_OFFSETS_FILENAME = "conversations_offsets.json"


def default_offset_path(project_root: str) -> Path:
    """Where incremental-read offsets for ``project_root`` are persisted."""
    return Path(project_root) / ".dot" / _OFFSETS_FILENAME


@dataclass
class ScanResult:
    """Outcome of one ingest scan."""

    transcripts_scanned: int = 0
    turns_read: int = 0
    decisions_captured: int = 0
    captured_memory_ids: list[str] = field(default_factory=list)
    errors: int = 0

    @property
    def newly_captured(self) -> int:
        """Distinct memories first seen in this scan (capture is idempotent)."""
        return len(set(self.captured_memory_ids))


class ConversationIngester:
    """Reads transcripts through a source and captures their decisions."""

    def __init__(
        self,
        store: Store,
        source: ConversationSource | None = None,
        offset_path: Path | None = None,
    ) -> None:
        self.store = store
        self.decisions = DecisionService(store)
        self.source = source or ClaudeCodeSource()
        # ``offset_path`` is optional: callers that don't care (the daemon)
        # get a lazily-created reader bound to <project_root>/.dot/...
        # configured the first time scan() runs for a given project.
        self._offset_path = offset_path
        self._incremental: IncrementalReader | None = (
            IncrementalReader(offset_path) if offset_path is not None else None
        )

    # ------------------------------------------------------------------
    # The scan
    # ------------------------------------------------------------------
    def scan(self, project_root: str, *, incremental: bool = True) -> ScanResult:
        """Scan this project's transcripts once and capture decisions.

        With ``incremental=True`` (the default), each transcript file is
        read from its last-known byte offset; otherwise the whole file is
        parsed. Either way capture is idempotent, so a full re-scan produces
        no duplicate memories.
        """
        result = ScanResult()
        transcript_dir = self.source.transcript_dir(project_root)
        if transcript_dir is None or not transcript_dir.exists():
            # The tool isn't installed/used here -- a silent no-op, not an error.
            return result

        # Lazily bind an incremental reader to this project's .dot/ directory
        # so callers (the daemon, the CLI) get incremental reads for free
        # without passing an explicit offset path.
        if incremental and self._incremental is None:
            self._incremental = IncrementalReader(default_offset_path(project_root))

        try:
            for transcript in self._iter_transcripts(project_root, incremental=incremental):
                result.transcripts_scanned += 1
                try:
                    self._ingest_transcript(transcript, project_root, result)
                except Exception:  # noqa: BLE001 -- one file must not abort the scan
                    logger.exception("failed ingesting transcript %s", transcript.path)
                    result.errors += 1
        finally:
            if self._incremental is not None:
                self._incremental.save()

        if result.decisions_captured:
            logger.info(
                "captured %d decisions from %d conversation transcripts",
                result.decisions_captured,
                result.transcripts_scanned,
            )
        return result

    def _iter_transcripts(
        self, project_root: str, *, incremental: bool
    ) -> list[TranscriptFile]:
        """Materialize the source's transcripts (a list, for error isolation)."""
        if incremental and self._incremental is not None:
            return self._iter_incremental(project_root)
        return list(self.source.iter_transcripts(project_root))

    def _iter_incremental(self, project_root: str) -> list[TranscriptFile]:
        """Read only the new tail of each transcript file."""
        directory = self.source.transcript_dir(project_root)
        if directory is None or not directory.is_dir():
            return []
        out: list[TranscriptFile] = []
        for path in sorted(directory.rglob("*.jsonl")):
            turns = self._incremental.read_new_turns(path, project_root=project_root)  # type: ignore[union-attr]
            if not turns:
                continue
            session_id = next((turn.session_id for turn in turns if turn.session_id), "")
            out.append(
                TranscriptFile(
                    path=path,
                    session_id=session_id,
                    project_root=project_root,
                    turns=turns,
                )
            )
        return out

    def _ingest_transcript(
        self,
        transcript: TranscriptFile,
        project_root: str,
        result: ScanResult,
    ) -> None:
        for turn in transcript.turns:
            result.turns_read += 1
            # session_id is per-turn, not per-file: a single transcript file
            # can interleave turns from different sessions, and each must be
            # tagged with its own session so the idempotent source id stays
            # correct (conversation:<session>, not the file's first session).
            for memory in self._capture_turn(turn):
                result.decisions_captured += 1
                result.captured_memory_ids.append(memory.memory_id)

    def _capture_turn(self, turn: ConversationTurn) -> list[Memory]:
        """Capture every decision-bearing block in one turn."""
        captured: list[Memory] = []
        for block in turn.text.split(_BLOCK_SPLIT):
            decision = self._block_to_decision(block, turn)
            if decision is None:
                continue
            memory = self.decisions.capture(decision)
            captured.append(memory)
        return captured

    @staticmethod
    def _block_to_decision(
        block: str, turn: ConversationTurn
    ) -> CapturedDecision | None:
        block = block.strip()
        if not block:
            return None
        # parse_decision is the existing pattern matcher; it returns the
        # highest-confidence match (or None for mundane text). The source id
        # encodes the session so two sessions can't collide, and is part of
        # the idempotent memory id (sha256(source::content)).
        session_id = turn.session_id or ""
        source = f"conversation:{session_id}" if session_id else "conversation"
        decision = parse_decision(block, source=source, created_at=turn.timestamp)
        if decision is None:
            return None
        if turn.cwd:
            decision.file_path = turn.cwd
        return decision

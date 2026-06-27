"""Claude Code transcript source.

Claude Code stores each session as an append-only JSONL file -- one JSON
object per line -- under ``~/.claude/projects/<encoded-path>/<session>.jsonl``
(overridable with ``$CLAUDE_CONFIG_DIR``). Each line is one event:

    {"type": "user"|"assistant"|"system", "message": {...},
     "sessionId": "...", "cwd": "...", "timestamp": "..."}

Two things make this source robust:

1. **Project mapping uses the per-line ``cwd`` field**, not the parent
   folder name. The folder name is the project path with ``/`` replaced by
   ``-``, which collides for distinct paths differing only in separators
   (anthropics/claude-code#29471). Reading ``cwd`` is exact.
2. **Incremental reading.** Transcripts are append-only and can be large, so
   :class:`IncrementalReader` remembers the byte offset it last read for
   each file and only processes the newly appended tail. Partial trailing
   lines (a write mid-flush) are skipped and re-tried next scan.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from dot.conversations.source import (
    ConversationTurn,
    TranscriptFile,
    matches_project,
)

logger = logging.getLogger(__name__)

# Block types that carry machine interchange, not decisions. Dropping them
# here keeps the text we feed to the decision parser focused on human/assistant
# prose, which is where rationales actually live.
_NOISE_BLOCK_TYPES = frozenset(
    {"tool_use", "tool_result", "server_tool_use", "web_search_tool_result"}
)

# Roles we extract prose from. "system" events are configuration, not decisions.
_SPOKEN_ROLES = frozenset({"user", "assistant"})


def claude_config_dir() -> Path:
    """The Claude Code config directory (``$CLAUDE_CONFIG_DIR`` or ``~/.claude``)."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override).expanduser() if override else Path.home() / ".claude"


def projects_dir() -> Path:
    """The directory Claude Code stores per-project session transcripts in."""
    return claude_config_dir() / "projects"


def _parse_timestamp(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        # Claude Code writes ISO-8601 with a timezone (Z or +00:00).
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _extract_text(content) -> str:
    """Pull human-readable text out of a message's ``content`` field.

    ``content`` is either a plain string (simple prompts) or a list of
    content blocks. We keep ``text`` blocks and skip ``tool_use`` /
    ``tool_result`` noise, joining surviving blocks with a blank line so
    decision-pattern matching (which splits on paragraph boundaries) works.
    """
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    pieces: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in _NOISE_BLOCK_TYPES:
            continue
        if block.get("type") == "text":
            text = block.get("text", "")
            if isinstance(text, str) and text.strip():
                pieces.append(text.strip())
    return "\n\n".join(pieces)


def parse_transcript(path: Path, project_root: str | None = None) -> TranscriptFile:
    """Parse one Claude Code JSONL transcript into ordered turns.

    Lines belonging to a different project (per their ``cwd``) are dropped
    when ``project_root`` is given. Malformed lines are skipped with a
    warning -- a corrupt line must never abort the whole file.
    """
    transcript = TranscriptFile(path=path)
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("cannot read transcript %s: %s", path, exc)
        return transcript

    for line_no, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("%s:%d is not valid JSON; skipping", path.name, line_no)
            continue
        if not isinstance(event, dict):
            continue

        role = event.get("type")
        if role not in _SPOKEN_ROLES:
            continue

        cwd = event.get("cwd") or ""
        if project_root is not None and not matches_project(cwd, project_root):
            continue

        message = event.get("message")
        if not isinstance(message, dict):
            continue
        text = _extract_text(message.get("content"))
        if not text:
            continue

        session_id = event.get("sessionId") or ""
        if not transcript.session_id and session_id:
            transcript.session_id = session_id
        if not transcript.project_root and cwd:
            transcript.project_root = cwd

        transcript.turns.append(
            ConversationTurn(
                role=role,
                text=text,
                timestamp=_parse_timestamp(event.get("timestamp")),
                session_id=session_id,
                cwd=cwd,
            )
        )

    try:
        transcript.size = path.stat().st_size
    except OSError:
        transcript.size = len(raw.encode("utf-8"))
    return transcript


class ClaudeCodeSource:
    """The built-in :class:`ConversationSource` for Claude Code transcripts."""

    def transcript_dir(self, project_root: str) -> Path | None:
        directory = projects_dir()
        if not directory.is_dir():
            return None
        return directory

    def iter_transcripts(self, project_root: str) -> Iterator[TranscriptFile]:
        directory = self.transcript_dir(project_root)
        if directory is None or not directory.is_dir():
            return
        # Glob every *.jsonl under the projects tree. We deliberately do NOT
        # trust the parent folder name to identify the project (it can
        # collide); per-line cwd filtering in parse_transcript is the source
        # of truth. This means we may open a few unrelated files and skip
        # all their turns -- cheap, and correctness-preserving.
        for path in sorted(directory.rglob("*.jsonl")):
            transcript = parse_transcript(path, project_root=project_root)
            # Only yield transcripts that actually belong to this project.
            if transcript.turns and matches_project(
                transcript.project_root or "", project_root
            ):
                yield transcript
            elif transcript.turns and not transcript.project_root:
                # Older transcripts without a cwd field: match (per the
                # err-on-the-side-of-capturing rule in matches_project).
                yield transcript


class _OffsetStore:
    """Persisted per-file byte offsets so reads are incremental.

    Stored as JSON at ``<dot_dir>/conversations_offsets.json``. The store is
    deliberately tiny (one number per scanned file) and tolerant of a
    missing/corrupt file -- a missing store means "start from the beginning",
    which is always safe because capture is idempotent.
    """

    def __init__(self, offset_path: Path) -> None:
        self._path = offset_path
        self._offsets: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._offsets = {
                    str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))
                }
        except (json.JSONDecodeError, ValueError, OSError):
            logger.warning("conversations offset store unreadable; re-reading all transcripts")
            self._offsets = {}

    def get(self, path: Path) -> int:
        return self._offsets.get(self._key(path), 0)

    def set(self, path: Path, offset: int) -> None:
        self._offsets[self._key(path)] = int(offset)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._offsets, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    @staticmethod
    def _key(path: Path) -> str:
        return str(path)


class IncrementalReader:
    """Reads transcript files incrementally, remembering byte offsets.

    Transcripts are append-only, so on each scan we seek to the last byte we
    processed and read only the tail. A line cut in half by a write mid-flush
    is *not* committed: we advance the offset only to the start of the final
    incomplete line, so the partial bytes are retried (and completed) next
    scan. This is what makes repeated scans cheap without losing data.
    """

    def __init__(self, offset_path: Path) -> None:
        self._offsets = _OffsetStore(offset_path)

    def read_new_turns(
        self,
        path: Path,
        project_root: str | None = None,
    ) -> list[ConversationTurn]:
        """Return turns from the unread tail of ``path``.

        Updates the stored offset to the end of the last *complete* line.
        """
        try:
            with path.open("rb") as handle:
                start = self._offsets.get(path)
                handle.seek(start)
                raw = handle.read()
        except OSError as exc:
            logger.warning("cannot read %s: %s", path, exc)
            return []

        # If the file shrank (truncated/replaced), restart from the top so
        # we don't miss rewritten content. We must distinguish that from the
        # normal "already at EOF, nothing new" case (both yield raw == b"")
        # by comparing the stored offset against the file's current size.
        if not raw and start > 0:
            try:
                current_size = path.stat().st_size
            except OSError:
                current_size = -1
            if 0 <= current_size < start:
                self._offsets.set(path, 0)
                return self.read_new_turns(path, project_root)
            # file size >= stored offset: no new bytes since last scan.
            return []

        # Split off a trailing partial line: keep full lines now, carry the
        # remainder forward by not advancing past it.
        text = raw.decode("utf-8", errors="replace")
        if text and not text.endswith("\n"):
            last_newline = text.rfind("\n")
            if last_newline == -1:
                # No complete line yet -- wait for the next scan.
                return []
            # Advance only past the last *complete* line; the trailing
            # partial bytes are retried (and completed) next scan.
            text = text[: last_newline + 1]
            advance_to = start + len(text.encode("utf-8"))
        else:
            advance_to = start + len(raw)

        turns: list[ConversationTurn] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("%s:%d (offset %d) not valid JSON; skipping", path.name, line_no, start)
                continue
            if not isinstance(event, dict):
                continue
            turn = _event_to_turn(event)
            if turn is None:
                continue
            if project_root is not None and not matches_project(turn.cwd, project_root):
                continue
            turns.append(turn)

        self._offsets.set(path, advance_to)
        return turns

    def save(self) -> None:
        self._offsets.save()

    @property
    def offsets(self) -> dict[str, int]:
        return dict(self._offsets._offsets)  # noqa: SLF001 -- read-only view for tests


def _event_to_turn(event: dict) -> ConversationTurn | None:
    """Convert one parsed JSONL event into a turn, or None if it's noise."""
    role = event.get("type")
    if role not in _SPOKEN_ROLES:
        return None
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    text = _extract_text(message.get("content"))
    if not text:
        return None
    return ConversationTurn(
        role=role,
        text=text,
        timestamp=_parse_timestamp(event.get("timestamp")),
        session_id=str(event.get("sessionId") or ""),
        cwd=str(event.get("cwd") or ""),
    )

"""The conversation-source contract.

A :class:`ConversationSource` knows how to:

- resolve where a particular tool keeps transcripts for a given project,
- yield :class:`TranscriptFile` handles lazily (so a huge history never
  loads all at once),
- parse each transcript into ordered :class:`ConversationTurn` objects,
  skipping tool-call noise that carries no decisions.

The built-in implementation is :class:`dot.conversations.claude_code.ClaudeCodeSource`;
the protocol exists so additional local sources (VS Code Copilot Chat,
Cursor, etc.) can be slotted in later without touching the ingest layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ConversationTurn:
    """One user or assistant contribution, stripped of tool-call noise.

    Only turns carrying human- or model-authored prose are kept: tool
    invocations and their machine results are dropped here because they
    almost never contain a rationale worth remembering. The :mod:`ingest`
    layer decides which of these turns actually yield decisions.
    """

    role: str  # "user" | "assistant"
    text: str
    timestamp: datetime | None = None
    session_id: str = ""
    cwd: str = ""  # the project directory the session was run in


@dataclass
class TranscriptFile:
    """A transcript file plus the project it was run in.

    ``project_root`` is resolved from the transcript's own ``cwd`` field,
    not from the parent directory name (which can collide -- see
    anthropics/claude-code#29471). A transcript may contain turns from
    several sessions; the file is the unit of incremental reading.
    """

    path: Path
    session_id: str = ""
    project_root: str = ""
    size: int = 0
    turns: list[ConversationTurn] = field(default_factory=list)


@runtime_checkable
class ConversationSource(Protocol):
    """A pluggable source of local conversation transcripts."""

    def transcript_dir(self, project_root: str) -> Path | None:
        """Where this tool keeps transcripts for ``project_root``.

        Returns ``None`` if the tool isn't installed/used here -- the
        feature then degrades to a silent no-op.
        """
        ...

    def iter_transcripts(self, project_root: str) -> Iterator[TranscriptFile]:
        """Yield transcripts belonging to ``project_root``, lazily.

        Each transcript carries its parsed turns. Files that fail to parse
        are skipped (with a log line), never raised.
        """
        ...


def matches_project(turn_cwd: str, project_root: str) -> bool:
    """Does a transcript turn's ``cwd`` belong to this Dot project?

    We compare resolved paths so trailing slashes, symlinks and case
    differences on case-insensitive filesystems don't cause false negatives.
    A turn with an empty ``cwd`` (older transcripts) is treated as a match:
    erring on the side of capturing beats silently dropping decisions.
    """
    if not turn_cwd:
        return True
    try:
        return Path(turn_cwd).resolve() == Path(project_root).resolve()
    except (OSError, ValueError):
        return turn_cwd.rstrip("/") == project_root.rstrip("/")

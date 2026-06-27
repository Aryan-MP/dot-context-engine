"""Automatic conversation capture.

Reads AI-tool conversation transcripts that live locally on disk (Claude
Code's JSONL session logs by default) and feeds decision-bearing text
through the existing memory pipeline -- no manual transcript paste, no
network.

The feature is opt-in (``capture_conversations`` config flag, wired up in
phase 2) and strictly local: it reads only ``~/.claude`` (or
``$CLAUDE_CONFIG_DIR``) and the project's ``.dot/`` directory. Nothing is
uploaded anywhere, ever.

- :mod:`dot.conversations.source` -- the pluggable source contract.
- :mod:`dot.conversations.claude_code` -- the built-in Claude Code source.
- :mod:`dot.conversations.ingest` -- wires transcripts into Dot's memory.
"""

from __future__ import annotations

from dot.conversations.claude_code import ClaudeCodeSource
from dot.conversations.ingest import ConversationIngester, ScanResult
from dot.conversations.source import (
    ConversationSource,
    ConversationTurn,
    TranscriptFile,
)
from dot.conversations.watcher import ConversationWatcher

__all__ = [
    "ClaudeCodeSource",
    "ConversationIngester",
    "ConversationSource",
    "ConversationTurn",
    "ConversationWatcher",
    "ScanResult",
    "TranscriptFile",
]

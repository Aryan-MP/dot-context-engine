"""Decision capture and retrieval.

Architectural decisions live in three places, and Dot mines all of them:
- git commit messages (and merged PR descriptions in merge commits)
- code comments tagged TODO/NOTE/DECISION or phrased as rationale
- AI conversations, captured via the API or VS Code extension

Each captured decision is stored as a Memory with kind="decision",
"action_item", or "rejected", tagged with its source.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from dot.memory.store import Memory, Store

logger = logging.getLogger(__name__)

# Phrases that signal a decision was made (and its rationale recorded).
DECISION_PATTERNS = [
    (re.compile(r"\bdecided to\b", re.I), "decision", 0.9),
    (re.compile(r"\bchose (\w[\w\s-]*) over (\w[\w\s-]*)", re.I), "decision", 0.95),
    (re.compile(r"\bswitch(?:ed)? (?:from .+ )?to\b", re.I), "decision", 0.7),
    (re.compile(r"\brefactor(?:ed)? .{0,60}because\b", re.I), "decision", 0.85),
    (re.compile(r"\bworkaround for\b", re.I), "decision", 0.8),
    (re.compile(r"\bfixed by\b", re.I), "decision", 0.6),
    (re.compile(r"\binstead of\b", re.I), "decision", 0.6),
    (re.compile(r"\btrade-?off\b", re.I), "decision", 0.7),
    (re.compile(r"\brejected\b|\bruled out\b|\bwon'?t (?:use|do)\b", re.I), "rejected", 0.8),
    (re.compile(r"\bTODO\b[:\s]", re.I), "action_item", 0.5),
    (re.compile(r"\bNOTE\b[:\s]", re.I), "note", 0.5),
    (re.compile(r"\bBREAKING\b|\bDEPRECAT", re.I), "decision", 0.9),
]

ISSUE_REFERENCE = re.compile(r"(?:#|GH-|JIRA-|[A-Z]{2,8}-)(\d+)")


@dataclass
class CapturedDecision:
    content: str
    kind: str  # decision | rejected | action_item | note
    confidence: float
    source: str
    file_path: str = ""
    created_at: datetime | None = None
    tags: list[str] = field(default_factory=list)


def parse_decision(message: str, source: str, created_at: datetime | None = None,
                   file_path: str = "") -> CapturedDecision | None:
    """Extract a structured decision from free text (commit message, comment).

    Returns the highest-confidence match, or None if the text doesn't look
    like it records a decision.
    """
    text = message.strip()
    if not text or len(text) < 12:
        return None

    best: tuple[str, float] | None = None
    for pattern, kind, confidence in DECISION_PATTERNS:
        if pattern.search(text):
            if best is None or confidence > best[1]:
                best = (kind, confidence)
    if best is None:
        return None

    kind, confidence = best
    tags = ["issue:" + ref for ref in ISSUE_REFERENCE.findall(text)[:5]]
    # Keep the message focused: subject + the first rationale-bearing lines.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    content = "\n".join(lines[:6])
    return CapturedDecision(
        content=content,
        kind=kind,
        confidence=confidence,
        source=source,
        file_path=file_path,
        created_at=created_at,
        tags=tags,
    )


def extract_decisions_from_git(repo_path: str, max_count: int = 500) -> list[CapturedDecision]:
    """Mine the git log for decisions recorded in commit messages."""
    try:
        import git
    except ImportError:
        logger.warning("GitPython not installed; skipping git decision mining")
        return []
    try:
        repo = git.Repo(repo_path, search_parent_directories=True)
    except Exception:
        logger.debug("%s is not a git repository", repo_path)
        return []

    decisions: list[CapturedDecision] = []
    try:
        commits = list(repo.iter_commits(max_count=max_count))
    except Exception:
        return []

    for commit in commits:
        message = commit.message if isinstance(commit.message, str) else commit.message.decode(
            "utf-8", errors="replace"
        )
        decision = parse_decision(
            message,
            source=f"git:{commit.hexsha[:12]}",
            created_at=datetime.fromtimestamp(commit.committed_date, tz=UTC),
        )
        if decision:
            # attach the most relevant touched file for proximity ranking
            try:
                touched = list(commit.stats.files)
                if touched:
                    decision.file_path = str(touched[0])
            except Exception:
                pass
            decision.tags.append(f"author:{commit.author.name}")
            decisions.append(decision)
    return decisions


class DecisionService:
    """Persists captured decisions into the store, idempotently."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def capture(self, decision: CapturedDecision) -> Memory:
        import hashlib

        # Deterministic id from source+content so re-mining git is idempotent.
        memory_id = hashlib.sha256(
            f"{decision.source}::{decision.content}".encode()
        ).hexdigest()[:36]
        return self.store.add_memory(
            content=decision.content,
            kind=decision.kind,
            source=decision.source,
            file_path=decision.file_path,
            tags=decision.tags,
            confidence=decision.confidence,
            created_at=decision.created_at,
            memory_id=memory_id,
        )

    def mine_git(self, max_count: int = 500) -> int:
        decisions = extract_decisions_from_git(self.store.config.project_root, max_count)
        for decision in decisions:
            self.capture(decision)
        if decisions:
            logger.info("captured %d decisions from git history", len(decisions))
        return len(decisions)

    def capture_from_conversation(self, transcript: str, source: str = "conversation") -> list[Memory]:
        """Extract decisions/action items from an AI conversation transcript."""
        captured: list[Memory] = []
        # Split on paragraph boundaries; evaluate each independently.
        for block in re.split(r"\n\s*\n", transcript):
            decision = parse_decision(block, source=source, created_at=datetime.now(UTC))
            if decision:
                captured.append(self.capture(decision))
        return captured

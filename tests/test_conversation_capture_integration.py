"""Integration tests for conversation capture through the daemon + API layers.

``tests/test_conversations.py`` covers the ingest *library* in isolation
(``ConversationIngester``, ``IncrementalReader``, ``ClaudeCodeSource``).
These tests drive the higher layers that ship in phase 2:

* ``Daemon.scan_conversations()`` — the daemon entrypoint wired in step 1/2.
* The opt-in ``capture_conversations`` config gate (off by default).
* The degradation path when ``~/.claude`` (``$CLAUDE_CONFIG_DIR``) is absent.
* The ``POST /conversations/scan`` REST endpoint and the ``/memory`` surface.

All tests are strictly local: they point ``CLAUDE_CONFIG_DIR`` at a throwaway
tmp dir, drop synthetic JSONL fixtures, and assert against in-process stores.
No network, no real ``~/.claude``, no uvicorn.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dot.api import create_app
from dot.config import ProjectConfig
from dot.daemon import Daemon

# The exact decision-bearing phrase confirmed (step 2 smokes) to match
# ``parse_decision``. Do not vary it without re-verifying capture first.
DECISION_TEXT = "We chose Redis over Memcached for caching."


def _evt(*, role: str, content, session_id: str = "sess-int-1", cwd: str, timestamp: str = "2026-06-26T10:00:00Z"):
    """Build one Claude-Code-style JSONL event."""
    return {
        "type": role,
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": timestamp,
        "message": {"role": role, "content": content},
    }


def _write_jsonl(path: Path, events: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    """A fake ``~/.claude`` pointing at CLAUDE_CONFIG_DIR under tmp_path."""
    home = tmp_path / "claude-home"
    home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    return home


@pytest.fixture
def project_root(tmp_path):
    """An initialized Dot project root the ingester will capture into."""
    (tmp_path / "src.py").write_text("x = 1\n")
    return tmp_path


def _config(project_root: Path, *, capture: bool) -> ProjectConfig:
    cfg = ProjectConfig(project_root=str(project_root))
    cfg.capture_conversations = capture
    cfg.save()
    return cfg


def _drop_decision_transcript(claude_home: Path, project_root: Path, *, session_id: str = "sess-int-1") -> Path:
    """Write one decision-bearing assistant turn under projects/<enc>/s.jsonl."""
    transcript = claude_home / "projects" / "enc" / "s.jsonl"
    return _write_jsonl(
        transcript,
        [_evt(role="assistant", content=DECISION_TEXT, session_id=session_id, cwd=str(project_root))],
    )


# ---------------------------------------------------------------------------
# Test A: capture surfaces a decision memory tagged with its session id
# ---------------------------------------------------------------------------

def test_capture_surfaces_decision_memory_with_session_source(claude_home, project_root):
    _drop_decision_transcript(claude_home, project_root)
    daemon = Daemon(_config(project_root, capture=True))

    result = daemon.scan_conversations()

    assert result["enabled"] is True
    assert result["transcripts_scanned"] >= 1
    assert result["decisions_captured"] >= 1

    mems = daemon.store.list_memories(limit=10000)
    conv = [m for m in mems if m.source == "conversation:sess-int-1"]
    assert conv, f"no conversation:sess-int-1 memory; sources={[m.source for m in mems]}"
    assert "Redis" in conv[0].content


# ---------------------------------------------------------------------------
# Test B: a second run captures nothing new (stable sha256 ids)
# ---------------------------------------------------------------------------

def test_capture_is_idempotent_on_rerun(claude_home, project_root):
    _drop_decision_transcript(claude_home, project_root)
    daemon = Daemon(_config(project_root, capture=True))

    first = daemon.scan_conversations()
    assert first["newly_captured"] >= 1
    count_after_first = len(daemon.store.list_memories(limit=10000))
    first_conv = [m for m in daemon.store.list_memories(limit=10000) if m.source == "conversation:sess-int-1"]
    assert first_conv
    first_id = first_conv[0].memory_id

    second = daemon.scan_conversations()
    assert second["newly_captured"] == 0, f"second run not idempotent: {second}"

    count_after_second = len(daemon.store.list_memories(limit=10000))
    assert count_after_second == count_after_first, "memory count grew on re-run"

    # Same memory id survives (no duplicate row created).
    second_conv = [m for m in daemon.store.list_memories(limit=10000) if m.source == "conversation:sess-int-1"]
    assert {m.memory_id for m in second_conv} == {first_id}


# ---------------------------------------------------------------------------
# Test C: capture enabled but ~/.claude absent -> no crash (daemon-start smoke)
# ---------------------------------------------------------------------------

def test_daemon_with_capture_enabled_does_not_crash_without_claude_home(tmp_path, monkeypatch):
    # CLAUDE_CONFIG_DIR points at an empty dir — no projects/ subtree, i.e.
    # Claude Code not installed. Daemon construction + scan + watcher lifecycle
    # must all degrade silently rather than crash.
    empty_home = tmp_path / "no-claude-here"
    empty_home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(empty_home))

    (tmp_path / "src.py").write_text("x = 1\n")

    # Construction builds a ConversationWatcher (degraded) — must not raise.
    daemon = Daemon(_config(tmp_path, capture=True))
    assert daemon._conversation_watcher is not None, "watcher should be built when enabled"

    # Scan returns an empty (but enabled) result — no exception.
    result = daemon.scan_conversations()
    assert result["enabled"] is True
    assert result["transcripts_scanned"] == 0
    assert result["decisions_captured"] == 0

    # Watcher start/stop are silent no-ops when the projects/ dir is absent.
    daemon._conversation_watcher.start()
    daemon._conversation_watcher.stop()


# ---------------------------------------------------------------------------
# Test D: capture disabled (default) -> disabled result, no memories, no watcher
# ---------------------------------------------------------------------------

def test_capture_disabled_returns_disabled_result(claude_home, project_root):
    # Even with a decision-bearing transcript present, capture stays off.
    _drop_decision_transcript(claude_home, project_root)
    daemon = Daemon(_config(project_root, capture=False))

    assert daemon._conversation_watcher is None

    result = daemon.scan_conversations()
    assert result["enabled"] is False

    conv = [m for m in daemon.store.list_memories(limit=10000) if m.source.startswith("conversation:")]
    assert conv == []


# ---------------------------------------------------------------------------
# Test E: the API endpoint surfaces the captured memory in /memory
# ---------------------------------------------------------------------------

def test_capture_via_api_endpoint_surfaces_memory(claude_home, project_root):
    _drop_decision_transcript(claude_home, project_root)
    daemon = Daemon(_config(project_root, capture=True))
    client = TestClient(create_app(daemon))

    # The enabled daemon scans synchronously and returns real counts.
    scan = client.post("/conversations/scan")
    assert scan.status_code == 200
    assert scan.json()["enabled"] is True
    assert scan.json()["decisions_captured"] >= 1

    # The captured decision must surface in GET /memory with the session source.
    mems = client.get("/memory").json()["memories"]
    conv = [m for m in mems if m["source"] == "conversation:sess-int-1"]
    assert conv, f"no conversation:sess-int-1 memory in /memory; sources={[m['source'] for m in mems]}"
    assert "Redis" in conv[0]["content"]

"""Tests for the conversation-capture ingest layer.

Synthetic JSONL fixtures exercise every behavior the ferment's success
criteria demand: user/assistant turn extraction, tool-call noise dropped,
multi-session files, project-mapping via the per-line cwd field, incremental
byte-offset tracking (a second scan reads nothing new), idempotent
double-capture (stable sha256 memory ids), and tolerance of malformed lines.

These tests are pure: they build a throwaway project under tmp_path, drop a
fake ``$CLAUDE_CONFIG_DIR`` tree of JSONL transcripts, run the ingester, and
assert against the resulting memories. No network, no real ~/.claude.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dot.config import ProjectConfig
from dot.conversations.claude_code import (
    ClaudeCodeSource,
    IncrementalReader,
    claude_config_dir,
    parse_transcript,
    projects_dir,
)
from dot.conversations.ingest import ConversationIngester, default_offset_path
from dot.conversations.source import matches_project
from dot.memory.store import Store

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
def project(tmp_path):
    """An initialized Dot project the ingester will capture into."""
    (tmp_path / "src.py").write_text("x = 1\n")
    config = ProjectConfig(project_root=str(tmp_path))
    config.save()
    return config


@pytest.fixture
def store(project):
    return Store(project)


def _evt(
    *,
    role: str,
    content,
    session_id: str = "sess-1",
    cwd: str | None = None,
    timestamp: str = "2026-06-26T10:00:00Z",
):
    """Build one Claude-Code-style JSONL event."""
    return {
        "type": role,
        "sessionId": session_id,
        "cwd": cwd if cwd is not None else "",
        "timestamp": timestamp,
        "message": {"role": role, "content": content},
    }


def _write_jsonl(path: Path, events: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Path resolution (CLAUDE_CONFIG_DIR)
# ---------------------------------------------------------------------------

def test_claude_config_dir_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "custom"))
    assert claude_config_dir() == tmp_path / "custom"
    assert projects_dir() == tmp_path / "custom" / "projects"


def test_claude_config_dir_defaults_to_home(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fake-home-xyz")
    # expanduser respects HOME on POSIX.
    assert claude_config_dir() == Path("/tmp/fake-home-xyz/.claude")


def test_transcript_dir_returns_none_when_projects_missing(claude_home):
    source = ClaudeCodeSource()
    # claude_home exists but has no projects/ subdir yet.
    assert source.transcript_dir("/any/project") is None


# ---------------------------------------------------------------------------
# parse_transcript: turn extraction & noise skipping
# ---------------------------------------------------------------------------

def test_parse_transcript_extracts_user_and_assistant_turns(tmp_path):
    tf = tmp_path / "s.jsonl"
    _write_jsonl(tf, [
        _evt(role="user", content="how should we store money?"),
        _evt(role="assistant", content="We decided to use Decimal over float."),
    ])
    transcript = parse_transcript(tf)
    assert [t.role for t in transcript.turns] == ["user", "assistant"]
    assert "Decimal" in transcript.turns[1].text


def test_parse_transcript_skips_tool_result_and_tool_use_blocks(tmp_path):
    tf = tmp_path / "s.jsonl"
    _write_jsonl(tf, [
        _evt(role="assistant", content=[
            {"type": "text", "text": "We chose Redis over Memcached."},
            {"type": "tool_use", "name": "Edit", "input": {}},
        ]),
        _evt(role="user", content=[
            {"type": "tool_result", "content": "file updated"},
        ]),
        _evt(role="assistant", content="All done."),
    ])
    transcript = parse_transcript(tf)
    # tool_result turn yields no text -> dropped entirely (2 turns, not 3).
    assert len(transcript.turns) == 2
    assert "Redis" in transcript.turns[0].text
    assert "All done" in transcript.turns[1].text


def test_parse_transcript_joins_multiple_text_blocks(tmp_path):
    tf = tmp_path / "s.jsonl"
    _write_jsonl(tf, [
        _evt(role="assistant", content=[
            {"type": "text", "text": "First paragraph."},
            {"type": "text", "text": "Second paragraph."},
        ]),
    ])
    transcript = parse_transcript(tf)
    assert transcript.turns[0].text == "First paragraph.\n\nSecond paragraph."


def test_parse_transcript_tolerates_malformed_lines(tmp_path):
    tf = tmp_path / "s.jsonl"
    # One good event, one garbage line, one good event.
    raw = (
        json.dumps(_evt(role="user", content="We decided to use SQLite.")) + "\n"
        + "this is not json at all\n"
        + "{broken json\n"
        + json.dumps(_evt(role="assistant", content="We ruled out MySQL.")) + "\n"
    )
    tf.write_text(raw, encoding="utf-8")
    transcript = parse_transcript(tf)
    # The two malformed lines are skipped, both valid turns survive.
    assert len(transcript.turns) == 2
    assert "SQLite" in transcript.turns[0].text
    assert "MySQL" in transcript.turns[1].text


def test_parse_transcript_skips_system_events(tmp_path):
    tf = tmp_path / "s.jsonl"
    _write_jsonl(tf, [
        {"type": "system", "message": {"content": "system prompt"}, "sessionId": "s"},
        _evt(role="user", content="We decided to use gRPC."),
    ])
    transcript = parse_transcript(tf)
    assert len(transcript.turns) == 1
    assert transcript.turns[0].role == "user"


# ---------------------------------------------------------------------------
# Project mapping via cwd (not folder-name encoding)
# ---------------------------------------------------------------------------

def test_matches_project_compares_resolved_paths(tmp_path):
    root = str(tmp_path)
    assert matches_project(root, root) is True
    assert matches_project(root + "/", root) is True  # trailing slash tolerant
    assert matches_project(str(tmp_path / "other"), root) is False


def test_matches_project_empty_cwd_is_a_match():
    # Older transcripts without cwd -> err on the side of capturing.
    assert matches_project("", "/some/project") is True


def test_parse_transcript_filters_turns_by_project_root(tmp_path):
    proj = tmp_path / "myproj"
    other = tmp_path / "otherproj"
    tf = tmp_path / "s.jsonl"
    _write_jsonl(tf, [
        _evt(role="user", content="belongs to myproj", cwd=str(proj)),
        _evt(role="user", content="belongs to other", cwd=str(other)),
    ])
    transcript = parse_transcript(tf, project_root=str(proj))
    assert len(transcript.turns) == 1
    assert "myproj" in transcript.turns[0].text


def test_iter_transcripts_only_yields_matching_project(claude_home, project):
    # Two sessions under the same encoded folder, different cwds.
    sess_dir = claude_home / "projects" / "encoded"
    other_root = project.project_root + "-unrelated"

    _write_jsonl(sess_dir / "mine.jsonl", [
        _evt(role="assistant", content="We decided to use Postgres.", cwd=project.project_root),
    ])
    _write_jsonl(sess_dir / "theirs.jsonl", [
        _evt(role="assistant", content="We chose MongoDB.", cwd=other_root),
    ])

    source = ClaudeCodeSource()
    transcripts = list(source.iter_transcripts(project.project_root))
    assert len(transcripts) == 1
    assert "Postgres" in transcripts[0].turns[0].text


# ---------------------------------------------------------------------------
# IncrementalReader: offset tracking
# ---------------------------------------------------------------------------

def test_incremental_reader_second_scan_reads_zero_new(tmp_path):
    tf = tmp_path / "s.jsonl"
    offsets = tmp_path / "offs.json"
    _write_jsonl(tf, [_evt(role="user", content="We decided to use Redis.")])

    reader = IncrementalReader(offsets)
    first = reader.read_new_turns(tf)
    assert len(first) == 1
    reader.save()
    assert offsets.exists()

    second = reader.read_new_turns(tf)
    assert second == [], "second scan with no appends must read zero new turns"


def test_incremental_reader_reads_only_appended_tail(tmp_path):
    tf = tmp_path / "s.jsonl"
    offsets = tmp_path / "offs.json"
    _write_jsonl(tf, [_evt(role="user", content="We decided to use Redis.", session_id="s1")])

    reader = IncrementalReader(offsets)
    reader.read_new_turns(tf)
    reader.save()

    # Append a second decision.
    with tf.open("a") as fh:
        fh.write(json.dumps(_evt(role="assistant", content="We chose Memcached.", session_id="s1")) + "\n")
    new_turns = reader.read_new_turns(tf)
    assert len(new_turns) == 1
    assert "Memcached" in new_turns[0].text
    reader.save()

    # And nothing more.
    assert reader.read_new_turns(tf) == []


def test_incremental_reader_holds_back_partial_trailing_line(tmp_path):
    tf = tmp_path / "s.jsonl"
    offsets = tmp_path / "offs.json"
    line = json.dumps(_evt(role="user", content="We decided to use gRPC.")) + "\n"
    tf.write_text(line, encoding="utf-8")

    reader = IncrementalReader(offsets)
    reader.read_new_turns(tf)
    reader.save()

    # Write only the first half of a new line.
    tf.write_text(line + line[: len(line) // 2], encoding="utf-8")
    assert reader.read_new_turns(tf) == [], "partial trailing line must not be consumed yet"

    # Complete it.
    with tf.open("a") as fh:
        fh.write(line[len(line) // 2 :])
    turns = reader.read_new_turns(tf)
    assert len(turns) == 1
    assert "gRPC" in turns[0].text


def test_incremental_reader_restarts_on_truncation(tmp_path):
    tf = tmp_path / "s.jsonl"
    offsets = tmp_path / "offs.json"
    # A long first line so the stored offset is well past any shorter rewrite.
    big = json.dumps(_evt(
        role="user",
        content="We decided to use Apache Kafka for event streaming because we need replay and ordering across consumers.",
    )) + "\n"
    tf.write_text(big, encoding="utf-8")

    reader = IncrementalReader(offsets)
    reader.read_new_turns(tf)
    reader.save()

    # Replace with a shorter file (truncation/rotation).
    small = json.dumps(_evt(role="user", content="Decided NATS.")) + "\n"
    tf.write_text(small, encoding="utf-8")
    turns = reader.read_new_turns(tf)
    assert len(turns) == 1, "truncated file must restart from the top"
    assert "NATS" in turns[0].text


def test_offset_store_tolerates_corrupt_file(tmp_path):
    offsets = tmp_path / "offs.json"
    offsets.write_text("{ this is not json", encoding="utf-8")
    reader = IncrementalReader(offsets)
    # Corrupt store resets to empty -> reads from the start, no exception.
    tf = tmp_path / "s.jsonl"
    _write_jsonl(tf, [_evt(role="user", content="We decided to use SQLite.")])
    assert len(reader.read_new_turns(tf)) == 1


# ---------------------------------------------------------------------------
# ConversationIngester: end-to-end capture + idempotency
# ---------------------------------------------------------------------------

def test_scan_captures_decisions_with_session_source_tag(claude_home, project, store):
    sess_dir = claude_home / "projects" / "encoded"
    _write_jsonl(sess_dir / "s1.jsonl", [
        _evt(role="assistant", content="We decided to use Decimal over float for money.",
             session_id="sess-abc", cwd=project.project_root),
    ])

    ingester = ConversationIngester(store, source=ClaudeCodeSource())
    result = ingester.scan(project.project_root)

    assert result.decisions_captured >= 1
    assert result.transcripts_scanned == 1
    memories = store.list_memories(limit=10000)
    assert any(m.source == "conversation:sess-abc" for m in memories)


def test_scan_is_idempotent_on_second_run(claude_home, project, store):
    sess_dir = claude_home / "projects" / "encoded"
    _write_jsonl(sess_dir / "s1.jsonl", [
        _evt(role="assistant", content="We decided to use Postgres for persistence.",
             session_id="sess-abc", cwd=project.project_root),
    ])

    ingester = ConversationIngester(store, source=ClaudeCodeSource())
    first = ingester.scan(project.project_root)
    count_after_first = len(store.list_memories(limit=10000))

    # Second incremental scan: offset advanced, nothing new, count stable.
    second = ingester.scan(project.project_root)
    assert second.turns_read == 0
    assert len(store.list_memories(limit=10000)) == count_after_first
    # And a full (non-incremental) re-scan is still idempotent (sha256 ids).
    ingester.scan(project.project_root, incremental=False)
    assert len(store.list_memories(limit=10000)) == count_after_first
    assert first.newly_captured >= 1


def test_scan_silent_noop_when_transcripts_absent(project, store):
    # No CLAUDE_CONFIG_DIR pointing at a populated tree.
    import os
    os.environ.pop("CLAUDE_CONFIG_DIR", None)
    ingester = ConversationIngester(store, source=ClaudeCodeSource())
    result = ingester.scan(project.project_root)
    assert result.transcripts_scanned == 0
    assert result.decisions_captured == 0
    assert result.errors == 0


def test_scan_multi_session_file_captures_each_decision(claude_home, project, store):
    # One .jsonl file containing turns from two distinct sessions.
    sess_dir = claude_home / "projects" / "encoded"
    _write_jsonl(sess_dir / "multi.jsonl", [
        _evt(role="assistant", content="We decided to use gRPC.", session_id="sess-a",
             cwd=project.project_root),
        _evt(role="assistant", content="We chose Redis over Memcached.", session_id="sess-b",
             cwd=project.project_root),
    ])

    ingester = ConversationIngester(store, source=ClaudeCodeSource())
    result = ingester.scan(project.project_root)
    assert result.decisions_captured >= 2

    memories = store.list_memories(limit=10000)
    sources = {m.source for m in memories}
    assert "conversation:sess-a" in sources
    assert "conversation:sess-b" in sources


def test_scan_skips_tool_result_only_turns(claude_home, project, store):
    sess_dir = claude_home / "projects" / "encoded"
    _write_jsonl(sess_dir / "s.jsonl", [
        _evt(role="user", content=[{"type": "tool_result", "content": "ok"}],
             session_id="s1", cwd=project.project_root),
        _evt(role="assistant", content="We decided to use SQLite.", session_id="s1",
             cwd=project.project_root),
    ])

    ingester = ConversationIngester(store, source=ClaudeCodeSource())
    result = ingester.scan(project.project_root)
    # tool_result yields no text -> not captured, but the assistant turn is.
    assert result.turns_read == 1
    assert result.decisions_captured >= 1


def test_scan_continues_past_malformed_line(claude_home, project, store):
    sess_dir = claude_home / "projects" / "encoded"
    tf = sess_dir / "s.jsonl"
    sess_dir.mkdir(parents=True, exist_ok=True)
    raw = (
        "this line is garbage\n"
        + json.dumps(_evt(role="assistant",
                         content="We decided to use NATS over Kafka.",
                         session_id="s1", cwd=project.project_root)) + "\n"
    )
    tf.write_text(raw, encoding="utf-8")

    ingester = ConversationIngester(store, source=ClaudeCodeSource())
    result = ingester.scan(project.project_root)
    assert result.decisions_captured >= 1
    assert result.errors == 0


def test_scan_default_offset_path_bound_lazily(claude_home, project, store):
    # No explicit offset_path passed -> should default under .dot/.
    assert default_offset_path(project.project_root) == \
        Path(project.project_root) / ".dot" / "conversations_offsets.json"

    sess_dir = claude_home / "projects" / "encoded"
    _write_jsonl(sess_dir / "s.jsonl", [
        _evt(role="assistant", content="We decided to cache embeddings.",
             session_id="s1", cwd=project.project_root),
    ])

    ingester = ConversationIngester(store, source=ClaudeCodeSource())
    assert ingester._incremental is None, "reader must be lazy until first scan"
    ingester.scan(project.project_root)
    assert ingester._incremental is not None
    # Offset file persisted at the default path.
    assert (Path(project.project_root) / ".dot" / "conversations_offsets.json").exists()

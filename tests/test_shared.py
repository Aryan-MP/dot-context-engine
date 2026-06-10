import json
from pathlib import Path

from dot.config import SHARED_MEMORIES_FILE, ProjectConfig
from dot.memory.shared import export_memory, import_shared


def test_share_and_reimport_roundtrip(daemon):
    store = daemon.store
    memory = store.add_memory("Chose JWT over sessions for the mobile API", kind="decision")

    assert export_memory(daemon.config, memory) is True
    shared_path = Path(daemon.config.project_root) / SHARED_MEMORIES_FILE
    assert shared_path.exists()
    record = json.loads(shared_path.read_text().strip())
    assert record["id"] == memory.memory_id
    assert record["content"].startswith("Chose JWT")
    assert "author" in record

    # sharing the same memory twice is a no-op
    assert export_memory(daemon.config, memory) is False
    assert len(shared_path.read_text().strip().splitlines()) == 1

    # already in the local store → import finds nothing new
    assert import_shared(store, daemon.config) == 0


def test_teammate_imports_shared_memories(daemon, tmp_path_factory):
    """Simulate a teammate's clone: same shared file, empty local store."""
    memory = daemon.store.add_memory("Decided to shard by tenant id", kind="decision")
    export_memory(daemon.config, memory)
    shared_content = (Path(daemon.config.project_root) / SHARED_MEMORIES_FILE).read_text()

    teammate_root = tmp_path_factory.mktemp("teammate-clone")
    (teammate_root / SHARED_MEMORIES_FILE).write_text(shared_content)
    teammate_config = ProjectConfig(project_root=str(teammate_root))
    teammate_config.save()

    from dot.daemon import Daemon

    teammate = Daemon(teammate_config)
    assert import_shared(teammate.store, teammate_config) == 1

    [imported] = teammate.store.list_memories(kind="decision")
    assert imported.memory_id == memory.memory_id
    assert "shared" in imported.tags
    assert any(tag.startswith("author:") for tag in imported.tags)

    # idempotent on re-import (e.g. repeated git pulls)
    assert import_shared(teammate.store, teammate_config) == 0


def test_import_skips_corrupt_lines(daemon):
    shared_path = Path(daemon.config.project_root) / SHARED_MEMORIES_FILE
    shared_path.write_text(
        'not json at all\n'
        '{"id": "", "content": "missing id"}\n'
        '{"id": "good-1", "kind": "decision", "content": "Chose Rust for the parser core"}\n'
    )
    assert import_shared(daemon.store, daemon.config) == 1
    [memory] = daemon.store.list_memories(kind="decision")
    assert memory.memory_id == "good-1"


def test_full_sync_imports_shared(daemon):
    shared_path = Path(daemon.config.project_root) / SHARED_MEMORIES_FILE
    shared_path.write_text(
        '{"id": "sync-1", "kind": "note", "content": "Team retro: keep modules under 400 lines"}\n'
    )
    result = daemon.full_sync()
    assert result["shared_imported"] == 1
    # the shared file itself must not be indexed as a code file
    assert not daemon.store.get_chunks_for_file(SHARED_MEMORIES_FILE)


def test_extra_extensions_config(tmp_path):
    (tmp_path / "notes.txt").write_text("challenge1: build the enterprise Copilot demo script")
    (tmp_path / "readme.md").write_text("# project")

    config = ProjectConfig(project_root=str(tmp_path))
    config.save()
    from dot.indexer.watcher import walk_project

    names = {p.name for p in walk_project(config)}
    assert "notes.txt" not in names  # not indexed by default

    config.extra_extensions = [".txt"]
    names = {p.name for p in walk_project(config)}
    assert "notes.txt" in names

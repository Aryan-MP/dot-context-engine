from datetime import UTC, datetime, timedelta

from dot.memory.decay import decayed_weight, is_forgettable, recency_score
from dot.memory.decisions import parse_decision


def test_decay_halves_at_half_life():
    created = datetime.now(UTC) - timedelta(days=30)
    weight = decayed_weight(created, confidence=1.0, half_life_days=30)
    assert abs(weight - 0.5) < 0.01


def test_access_reinforces_against_decay():
    created = datetime.now(UTC) - timedelta(days=60)
    untouched = decayed_weight(created, half_life_days=30, access_count=0)
    frequently_used = decayed_weight(created, half_life_days=30, access_count=20)
    assert frequently_used > untouched


def test_old_unused_memories_become_forgettable():
    created = datetime.now(UTC) - timedelta(days=365)
    assert is_forgettable(decayed_weight(created, half_life_days=30))


def test_recency_score_decays():
    fresh = recency_score(datetime.now(UTC))
    stale = recency_score(datetime.now(UTC) - timedelta(days=14))
    assert fresh > 0.95
    assert stale < 0.1


def test_parse_decision_detects_choices():
    decision = parse_decision(
        "Switch session storage: chose Redis over Memcached for persistence support",
        source="git:abc123",
    )
    assert decision is not None
    assert decision.kind == "decision"
    assert decision.confidence >= 0.9


def test_parse_decision_detects_rejections():
    decision = parse_decision(
        "We ruled out GraphQL for the public API; REST is enough. Fixes #42",
        source="git:def456",
    )
    assert decision is not None
    assert decision.kind == "rejected"
    assert "issue:42" in decision.tags


def test_parse_decision_ignores_mundane_commits():
    assert parse_decision("fix typo", source="git:aaa") is None
    assert parse_decision("bump version to 1.2.3", source="git:bbb") is None


def test_store_memory_roundtrip(daemon):
    store = daemon.store
    memory = store.add_memory(
        "Decided to use SQLite over Postgres for local-first storage",
        kind="decision", tags=["storage"],
    )
    results = store.query_memories("which database do we use", n=3)
    assert any(result.memory_id == memory.memory_id for result in results)

    listed = store.list_memories(kind="decision")
    assert len(listed) == 1

    assert store.delete_memory(memory.memory_id)
    assert store.list_memories(kind="decision") == []


def test_forget_pattern(daemon):
    store = daemon.store
    store.add_memory("Decided to use tabs not spaces", kind="decision")
    store.add_memory("Decided to deploy on Fridays", kind="decision")
    removed = store.forget_pattern("tabs")
    assert removed == 1
    assert len(store.list_memories()) == 1


def test_export_memories(daemon):
    daemon.store.add_memory("Chose pytest over unittest", kind="decision")
    exported = daemon.store.export_memories()
    assert len(exported) == 1
    assert exported[0]["kind"] == "decision"
    assert "created_at" in exported[0]

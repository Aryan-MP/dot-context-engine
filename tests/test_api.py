import pytest
from fastapi.testclient import TestClient

from dot.api import create_app


@pytest.fixture
def client(daemon):
    daemon.full_sync()
    return TestClient(create_app(daemon))


def test_status(client):
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["files_indexed"] >= 2
    assert data["chunks"] > 0


def test_context_raw(client):
    response = client.get("/context", params={"query": "authorize payment", "fmt": "raw"})
    assert response.status_code == 200
    data = response.json()
    assert data["chunks"]
    assert data["tokens_used"] <= data["token_budget"]


def test_context_claude_format(client):
    response = client.get(
        "/context",
        params={"query": "payments", "fmt": "claude", "file": "billing/payments.py"},
    )
    assert response.status_code == 200
    assert response.text.startswith("<codebase_context>")
    assert "x-dot-assembly-ms" in response.headers


def test_context_rejects_bad_format(client):
    assert client.get("/context", params={"fmt": "yaml"}).status_code == 422


def test_memory_crud(client):
    created = client.post(
        "/memory",
        json={"content": "Decided to pin Python 3.11 for tree-sitter wheels", "kind": "decision"},
    )
    assert created.status_code == 201
    memory_id = created.json()["id"]

    listed = client.get("/memory").json()["memories"]
    assert any(memory["id"] == memory_id for memory in listed)

    searched = client.get("/memory", params={"query": "python version"}).json()["memories"]
    assert any(memory["id"] == memory_id for memory in searched)

    assert client.delete(f"/memory/{memory_id}").status_code == 200
    assert client.delete(f"/memory/{memory_id}").status_code == 404


def test_conversation_capture(client):
    transcript = (
        "User: should we cache embeddings?\n\n"
        "Assistant: yes — we decided to cache embeddings by content hash "
        "because re-embedding unchanged files wastes 90% of indexing time.\n\n"
        "TODO: add an LRU bound on the cache."
    )
    response = client.post("/memory/conversation", json={"transcript": transcript})
    assert response.status_code == 201
    assert response.json()["captured"] >= 2


def test_graph(client):
    response = client.get("/graph")
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) >= 2
    # refunds.py imports billing.payments — should resolve to an internal edge
    assert any(edge["internal"] for edge in data["edges"])


def test_ask(client):
    response = client.post("/ask", json={"question": "how are refunds processed"})
    assert response.status_code == 200
    assert "refund" in response.text.lower()


def test_sync(client):
    response = client.post("/sync", json={"force": False})
    assert response.status_code == 202

from dot.integrations.mcp import McpServer


def _call(server: McpServer, method: str, params: dict | None = None, msg_id: int | None = 1):
    message: dict = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        message["id"] = msg_id
    if params is not None:
        message["params"] = params
    return server.handle(message)


def test_initialize_handshake(daemon):
    server = McpServer(daemon.config.project_root)
    response = _call(server, "initialize", {"protocolVersion": "2024-11-05"})
    assert response["result"]["serverInfo"]["name"] == "dot"
    assert "tools" in response["result"]["capabilities"]
    # notifications get no response
    assert _call(server, "notifications/initialized", msg_id=None) is None


def test_tools_list(daemon):
    server = McpServer(daemon.config.project_root)
    response = _call(server, "tools/list")
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {"dot_context", "dot_remember", "dot_status"}
    for tool in response["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"


def test_tool_remember_then_context(daemon):
    daemon.full_sync()
    server = McpServer(daemon.config.project_root)

    remembered = _call(
        server, "tools/call",
        {"name": "dot_remember", "arguments": {"content": "Chose Decimal over float for money"}},
    )
    assert remembered["result"]["isError"] is False
    assert "Recorded decision" in remembered["result"]["content"][0]["text"]

    context = _call(
        server, "tools/call",
        {"name": "dot_context", "arguments": {"query": "how do we authorize payments"}},
    )
    text = context["result"]["content"][0]["text"]
    assert context["result"]["isError"] is False
    assert "authorize" in text


def test_tool_remember_share_writes_jsonl(daemon):
    from pathlib import Path

    from dot.config import SHARED_MEMORIES_FILE

    server = McpServer(daemon.config.project_root)
    response = _call(
        server, "tools/call",
        {"name": "dot_remember",
         "arguments": {"content": "Decided to pin Node 20 in CI", "share": True}},
    )
    assert "Shared" in response["result"]["content"][0]["text"]
    assert (Path(daemon.config.project_root) / SHARED_MEMORIES_FILE).exists()


def test_unknown_tool_and_method(daemon):
    server = McpServer(daemon.config.project_root)
    bad_tool = _call(server, "tools/call", {"name": "nope", "arguments": {}})
    assert bad_tool["error"]["code"] == -32602
    bad_method = _call(server, "wat/wat")
    assert bad_method["error"]["code"] == -32601


def test_ping(daemon):
    server = McpServer(daemon.config.project_root)
    assert _call(server, "ping")["result"] == {}

"""MCP (Model Context Protocol) server over stdio.

Gives Claude Code (and any MCP client) native tools backed by the local Dot
store — no daemon required, no extra dependencies. Registered per-project via
.mcp.json (written by ``dot init``):

    {"mcpServers": {"dot": {"command": "dot", "args": ["mcp"]}}}

Implements the minimal protocol surface MCP clients need: ``initialize``,
``tools/list``, ``tools/call``, and ``ping``, speaking newline-delimited
JSON-RPC 2.0 on stdin/stdout. Logs go to stderr only — stdout belongs to
the protocol.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from dot import __version__

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "dot_context",
        "description": (
            "Retrieve relevant code chunks and recorded architectural decisions "
            "for this project from Dot's local index. Use for project-specific "
            "questions: how something is implemented, why a choice was made, or "
            "which files relate to a topic."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language question or topic",
                },
                "file": {
                    "type": "string",
                    "description": "Optional current file path for proximity ranking",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "dot_remember",
        "description": (
            "Record an architectural decision, rejected approach, or important "
            "note into Dot's project memory so future sessions (in any AI tool) "
            "know about it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "What was decided, and why"},
                "kind": {
                    "type": "string",
                    "enum": ["decision", "rejected", "action_item", "note"],
                    "description": "Kind of memory (default: decision)",
                },
                "share": {
                    "type": "boolean",
                    "description": "Also append to the committed dot-memories.jsonl so teammates get it",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "dot_status",
        "description": "What Dot knows about this project: files indexed, chunks, memories.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class McpServer:
    """One project-scoped MCP session. Lazily builds the store on first use."""

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self._assembler = None
        self._store = None
        self._config = None

    def _ensure_loaded(self):
        if self._store is None:
            from pathlib import Path

            from dot.config import ProjectConfig
            from dot.context.assembler import ContextAssembler
            from dot.memory.store import Store

            self._config = ProjectConfig.load(Path(self.project_root))
            self._store = Store(self._config)
            self._assembler = ContextAssembler(self._store, self._config)
        return self._store, self._assembler, self._config

    # ---- tool implementations ----

    def tool_dot_context(self, args: dict) -> str:
        from dot.context.formatter import format_context

        _store, assembler, _config = self._ensure_loaded()
        context = assembler.assemble(
            query=args.get("query", ""), current_file=args.get("file")
        )
        if context.is_empty:
            return "Dot has no indexed context for this query yet. Run `dot sync` first."
        return format_context(context, "markdown")

    def tool_dot_remember(self, args: dict) -> str:
        store, _assembler, config = self._ensure_loaded()
        content = args.get("content", "").strip()
        if len(content) < 3:
            return "Nothing recorded: content too short."
        memory = store.add_memory(
            content=content,
            kind=args.get("kind", "decision"),
            source="claude-code",
        )
        message = f"Recorded {memory.kind} {memory.memory_id[:8]}."
        if args.get("share"):
            from dot.memory.shared import export_memory

            if export_memory(config, memory):
                message += " Shared via dot-memories.jsonl (commit it to publish to the team)."
        return message

    def tool_dot_status(self, _args: dict) -> str:
        store, _assembler, _config = self._ensure_loaded()
        stats = store.stats()
        return json.dumps(stats, indent=2)

    # ---- protocol plumbing ----

    def handle(self, message: dict) -> dict | None:
        method = message.get("method")
        msg_id = message.get("id")
        is_notification = msg_id is None

        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "dot", "version": __version__},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params") or {}
                tool_name = params.get("name", "")
                tool_args = params.get("arguments") or {}
                handler = getattr(self, f"tool_{tool_name}", None)
                if handler is None:
                    return _error(msg_id, -32602, f"unknown tool: {tool_name}")
                text = handler(tool_args)
                result = {"content": [{"type": "text", "text": text}], "isError": False}
            elif is_notification:
                return None  # notifications/initialized etc. — nothing to do
            else:
                return _error(msg_id, -32601, f"method not found: {method}")
        except Exception as exc:
            logger.exception("error handling %s", method)
            if is_notification:
                return None
            if method == "tools/call":
                return _result(msg_id, {
                    "content": [{"type": "text", "text": f"dot error: {exc}"}],
                    "isError": True,
                })
            return _error(msg_id, -32603, str(exc))

        return None if is_notification else _result(msg_id, result)

    def serve_forever(self) -> None:
        """Read newline-delimited JSON-RPC from stdin until EOF."""
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                _write(_error(None, -32700, "parse error"))
                continue
            response = self.handle(message)
            if response is not None:
                _write(response)


def _result(msg_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _write(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve(project_root: str) -> None:
    McpServer(project_root).serve_forever()

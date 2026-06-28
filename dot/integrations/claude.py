"""Claude Code integration.

Three pieces, all wired by ``dot init`` when the claude integration is on:
1. A CLAUDE.md section telling Claude how to query Dot's API.
2. A SessionStart hook in .claude/settings.json that injects context when a
   session begins.
3. A project .mcp.json registering ``dot mcp`` as an MCP server, so Claude
   Code gets native dot_context / dot_remember / dot_status tools.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from dot.config import ProjectConfig

logger = logging.getLogger(__name__)

CLAUDE_MD_TEMPLATE = """
## Dot context memory

This project runs [Dot](https://github.com/Aryan-MP/dot-context-engine),
a local context daemon. Prefer the MCP tools (dot_context, dot_remember,
dot_status) when available; the REST API works from any shell:

- `curl 'http://{host}:{port}/context?query=<your question>&fmt=claude'`
- `curl 'http://{host}:{port}/memory'` — captured architectural decisions
- `curl -X POST http://{host}:{port}/memory -H 'content-type: application/json' \\
   -d '{{"content": "<decision>", "kind": "decision"}}'` — record a new decision

Record significant architectural decisions to Dot when you make them.
""".strip()


def _session_start_hook(host: str, port: int) -> list:
    return [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        f"curl -s --max-time 2 "
                        f"'http://{host}:{port}/context?query=session%20start&fmt=claude' "
                        "|| true"
                    ),
                }
            ]
        }
    ]


def install(config: ProjectConfig) -> list[str]:
    """Wire Dot into Claude Code for this project. Returns actions taken."""
    actions: list[str] = []
    root = Path(config.project_root)
    host, port = config.api_host, config.api_port
    section = CLAUDE_MD_TEMPLATE.format(host=host, port=port)

    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        existing = claude_md.read_text()
        if "Dot context memory" not in existing:
            claude_md.write_text(existing.rstrip() + "\n\n" + section + "\n")
            actions.append("appended Dot section to CLAUDE.md")
    else:
        claude_md.write_text(section + "\n")
        actions.append("created CLAUDE.md with Dot section")

    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(exist_ok=True)
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            logger.warning("could not parse %s; not modifying it", settings_path)
            settings = None  # type: ignore[assignment]
    if settings is not None:
        hooks = settings.setdefault("hooks", {})
        if "SessionStart" not in hooks:
            hooks["SessionStart"] = _session_start_hook(host, port)
            settings_path.write_text(json.dumps(settings, indent=2) + "\n")
            actions.append("added SessionStart hook to .claude/settings.json")

    actions.extend(install_mcp(config))
    return actions


def install_mcp(config: ProjectConfig) -> list[str]:
    """Register the Dot MCP server in the project's .mcp.json. Idempotent."""
    mcp_path = Path(config.project_root) / ".mcp.json"
    mcp_config: dict = {}
    if mcp_path.exists():
        try:
            mcp_config = json.loads(mcp_path.read_text())
        except json.JSONDecodeError:
            logger.warning("could not parse %s; not modifying it", mcp_path)
            return []
    servers = mcp_config.setdefault("mcpServers", {})
    if "dot" in servers:
        return []
    servers["dot"] = {"command": "dot", "args": ["mcp"]}
    mcp_path.write_text(json.dumps(mcp_config, indent=2) + "\n")
    return ["registered Dot MCP server in .mcp.json"]

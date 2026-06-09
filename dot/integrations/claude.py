"""Claude Code integration.

Two pieces:
1. ``dot claude install`` writes a CLAUDE.md include + a SessionStart hook
   into the project's .claude/settings.json so every Claude Code session
   starts with Dot's assembled context.
2. ``render_claude_context`` produces the XML-tagged context payload the
   hook injects (also available at GET /context?fmt=claude).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from dot.config import ProjectConfig

logger = logging.getLogger(__name__)

CLAUDE_MD_SECTION = """
## Dot context memory

This project runs [Dot](https://github.com/aryanp-spektra/dot-context-engine),
a local context daemon. Query it for relevant code and past decisions:

- `curl 'http://127.0.0.1:7337/context?query=<your question>&fmt=claude'`
- `curl 'http://127.0.0.1:7337/memory'` — captured architectural decisions
- `curl -X POST http://127.0.0.1:7337/memory -H 'content-type: application/json' \\
   -d '{"content": "<decision>", "kind": "decision"}'` — record a new decision

Record significant architectural decisions to Dot when you make them.
""".strip()

SESSION_START_HOOK = {
    "hooks": {
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "curl -s --max-time 2 "
                            "'http://127.0.0.1:7337/context?query=session%20start&fmt=claude' "
                            "|| true"
                        ),
                    }
                ]
            }
        ]
    }
}


def install(config: ProjectConfig) -> list[str]:
    """Wire Dot into Claude Code for this project. Returns actions taken."""
    actions: list[str] = []
    root = Path(config.project_root)

    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        existing = claude_md.read_text()
        if "Dot context memory" not in existing:
            claude_md.write_text(existing.rstrip() + "\n\n" + CLAUDE_MD_SECTION + "\n")
            actions.append("appended Dot section to CLAUDE.md")
    else:
        claude_md.write_text(CLAUDE_MD_SECTION + "\n")
        actions.append("created CLAUDE.md with Dot section")

    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(exist_ok=True)
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            logger.warning("could not parse %s; not modifying it", settings_path)
            return actions
    hooks = settings.setdefault("hooks", {})
    if "SessionStart" not in hooks:
        hooks["SessionStart"] = SESSION_START_HOOK["hooks"]["SessionStart"]
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        actions.append("added SessionStart hook to .claude/settings.json")
    return actions

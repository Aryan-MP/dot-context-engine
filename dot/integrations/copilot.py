"""Copilot context bridge.

GitHub Copilot can't call arbitrary local APIs, so Dot bridges context in
two ways:

1. The VS Code extension (vscode-extension/) queries /context on file
   switch and injects via the Language Model API — the rich path.
2. ``write_instructions_file`` maintains .github/copilot-instructions.md
   with a compact, periodically refreshed summary of what Dot knows —
   the zero-extension fallback that plain Copilot picks up natively.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from dot.config import ProjectConfig
from dot.memory.store import Store

logger = logging.getLogger(__name__)

MARKER_BEGIN = "<!-- dot:begin -->"
MARKER_END = "<!-- dot:end -->"
MAX_DECISIONS = 12


def render_instructions(store: Store) -> str:
    stats = store.stats()
    decisions = store.list_memories(limit=MAX_DECISIONS)
    lines = [
        MARKER_BEGIN,
        "## Project memory (maintained by Dot — do not edit this section)",
        f"_Indexed {stats['files_indexed']} files, {stats['memories']} captured decisions. "
        f"Updated {datetime.now(UTC).date().isoformat()}._",
        "",
    ]
    if decisions:
        lines.append("Key decisions and context:")
        for memory in decisions:
            flattened = " ".join(memory.content.split())[:200]
            lines.append(f"- ({memory.kind}) {flattened}")
    lines.append(MARKER_END)
    return "\n".join(lines)


def write_instructions_file(store: Store, config: ProjectConfig | None = None) -> Path:
    """Create/refresh the Dot section of .github/copilot-instructions.md."""
    config = config or store.config
    path = Path(config.project_root) / ".github" / "copilot-instructions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    section = render_instructions(store)

    if path.exists():
        existing = path.read_text()
        if MARKER_BEGIN in existing and MARKER_END in existing:
            before = existing.split(MARKER_BEGIN)[0]
            after = existing.split(MARKER_END, 1)[1]
            path.write_text(before + section + after)
        else:
            path.write_text(existing.rstrip() + "\n\n" + section + "\n")
    else:
        path.write_text(section + "\n")
    logger.info("refreshed %s", path)
    return path

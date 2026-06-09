"""Format assembled context for different AI tool consumers.

- "claude":  XML-tagged, rich — matches how Claude likes structured context
- "copilot": concise comment-style preamble, token-frugal
- "markdown": readable markdown for chat tools and humans
- "raw":     JSON for custom integrations
"""

from __future__ import annotations

import json
from pathlib import PurePath

from dot.context.assembler import AssembledContext

FORMATS = ("claude", "copilot", "markdown", "raw")


def format_context(context: AssembledContext, fmt: str = "claude") -> str:
    fmt = fmt.lower()
    if fmt == "claude":
        return _format_claude(context)
    if fmt == "copilot":
        return _format_copilot(context)
    if fmt == "markdown":
        return _format_markdown(context)
    if fmt == "raw":
        return json.dumps(context_to_dict(context), indent=2)
    raise ValueError(f"unknown format {fmt!r}; expected one of {FORMATS}")


def context_to_dict(context: AssembledContext) -> dict:
    return {
        "query": context.query,
        "current_file": context.current_file,
        "profile": context.profile,
        "token_budget": context.token_budget,
        "tokens_used": context.tokens_used,
        "assembly_ms": round(context.assembly_ms, 2),
        "chunks": [
            {
                "file_path": item.chunk.file_path,
                "symbol": item.chunk.symbol,
                "kind": item.chunk.kind,
                "start_line": item.chunk.start_line,
                "end_line": item.chunk.end_line,
                "language": item.chunk.language,
                "content": item.chunk.content,
                "score": round(item.score, 4),
                "score_components": {k: round(v, 4) for k, v in item.components.items()},
            }
            for item in context.chunks
        ],
        "decisions": [
            {
                "id": memory.memory_id,
                "kind": memory.kind,
                "content": memory.content,
                "source": memory.source,
                "file_path": memory.file_path,
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
                "weight": round(memory.weight, 4),
            }
            for memory in context.decisions
        ],
    }


def _format_claude(context: AssembledContext) -> str:
    parts = ["<codebase_context>"]
    if context.current_file:
        parts.append(f"  <current_file>{context.current_file}</current_file>")
    if context.decisions:
        parts.append("  <decisions>")
        for memory in context.decisions:
            timestamp = memory.created_at.date().isoformat() if memory.created_at else "unknown"
            parts.append(
                f'    <decision kind="{memory.kind}" source="{memory.source}" date="{timestamp}">'
            )
            parts.append(f"      {memory.content}")
            parts.append("    </decision>")
        parts.append("  </decisions>")
    if context.chunks:
        parts.append("  <code_chunks>")
        for item in context.chunks:
            chunk = item.chunk
            parts.append(
                f'    <chunk file="{chunk.file_path}" symbol="{chunk.symbol}" '
                f'lines="{chunk.start_line}-{chunk.end_line}" relevance="{item.score:.2f}">'
            )
            parts.append(chunk.content)
            parts.append("    </chunk>")
        parts.append("  </code_chunks>")
    parts.append("</codebase_context>")
    return "\n".join(parts)


def _format_copilot(context: AssembledContext) -> str:
    """Concise inline-comment style: Copilot context windows are tight."""
    lines = ["// Context from Dot (local codebase memory):"]
    for memory in context.decisions:
        lines.append(f"// [{memory.kind}] {_one_line(memory.content, 140)}")
    for item in context.chunks:
        chunk = item.chunk
        name = PurePath(chunk.file_path).name
        lines.append(f"// --- {name}:{chunk.start_line} {chunk.symbol} ---")
        lines.extend(chunk.content.splitlines())
    return "\n".join(lines)


def _format_markdown(context: AssembledContext) -> str:
    parts = ["## Codebase context (from Dot)"]
    if context.current_file:
        parts.append(f"**Current file:** `{context.current_file}`")
    if context.decisions:
        parts.append("\n### Relevant decisions")
        for memory in context.decisions:
            timestamp = memory.created_at.date().isoformat() if memory.created_at else ""
            parts.append(f"- **{memory.kind}** ({memory.source}, {timestamp}): {_one_line(memory.content, 300)}")
    if context.chunks:
        parts.append("\n### Relevant code")
        for item in context.chunks:
            chunk = item.chunk
            parts.append(
                f"\n**`{chunk.file_path}:{chunk.start_line}-{chunk.end_line}`** — "
                f"`{chunk.symbol}` (relevance {item.score:.2f})"
            )
            parts.append(f"```{chunk.language}\n{chunk.content}\n```")
    return "\n".join(parts)


def _one_line(text: str, max_length: int) -> str:
    flattened = " ".join(text.split())
    return flattened[: max_length - 1] + "…" if len(flattened) > max_length else flattened

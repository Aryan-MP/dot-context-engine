"""dot-context — the context assembly engine.

Given a query, current file, and recent activity, assembles the most
relevant context window and formats it for the consuming AI tool.
"""

from dot.context.assembler import ContextAssembler
from dot.context.formatter import format_context
from dot.context.ranker import rank_and_deduplicate, score_chunk

__all__ = ["ContextAssembler", "format_context", "rank_and_deduplicate", "score_chunk"]

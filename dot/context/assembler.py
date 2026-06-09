"""Context assembly engine — the core product value.

Implements the canonical algorithm:

1. vector-search chunks similar to the query
2. add file-proximity chunks (same module/package as the current file)
3. add recently modified chunks
4. pull relevant decisions/memories
5. rank + deduplicate everything
6. greedily fill the token budget from the top
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from dot.config import ProjectConfig
from dot.context.ranker import ScoredChunk, rank_and_deduplicate
from dot.indexer.chunker import estimate_tokens
from dot.memory.store import Memory, Store

# Reserve a slice of the budget for decisions — they're small and dense
# with "why", which code chunks can't provide.
DECISION_BUDGET_FRACTION = 0.2


@dataclass
class AssembledContext:
    query: str
    current_file: str | None
    chunks: list[ScoredChunk]
    decisions: list[Memory]
    token_budget: int
    tokens_used: int
    assembly_ms: float
    profile: str = "default"

    @property
    def is_empty(self) -> bool:
        return not self.chunks and not self.decisions


@dataclass
class ContextProfile:
    name: str = "default"
    token_budget: int = 4000
    n_chunks: int = 20
    include_decisions: bool = True

    @classmethod
    def from_config(cls, config: ProjectConfig, name: str | None) -> ContextProfile:
        if name and name in config.profiles:
            raw = config.profiles[name]
            return cls(
                name=name,
                token_budget=int(raw.get("token_budget", config.token_budget)),
                n_chunks=int(raw.get("n_chunks", 20)),
                include_decisions=bool(raw.get("include_decisions", True)),
            )
        return cls(token_budget=config.token_budget)


class ContextAssembler:
    def __init__(self, store: Store, config: ProjectConfig | None = None) -> None:
        self.store = store
        self.config = config or store.config

    def assemble(
        self,
        query: str,
        current_file: str | None = None,
        token_budget: int | None = None,
        profile: str | None = None,
    ) -> AssembledContext:
        started = time.perf_counter()
        prof = ContextProfile.from_config(self.config, profile)
        budget = token_budget or prof.token_budget

        # The query may be empty when a tool just wants "context for this
        # file" — fall back to the file path as the semantic anchor.
        effective_query = query.strip() or (current_file or "project overview")

        # 1. semantically similar chunks
        similar = self.store.query_chunks(effective_query, n_results=prof.n_chunks)
        # 2. file-proximity chunks
        proximate = self.store.get_proximate_chunks(current_file, n=10) if current_file else []
        # 2b. chunks from the current file itself rank highest on proximity
        own = self.store.get_chunks_for_file(current_file) if current_file else []
        # 3. recently modified chunks
        recent = self.store.get_recent_chunks(hours=24, n=10)
        # 4. relevant decisions/memories
        decisions = (
            self.store.query_memories(effective_query, n=5) if prof.include_decisions else []
        )

        # 5. score and deduplicate
        scored = rank_and_deduplicate(
            similar + proximate + own + recent,
            current_file=current_file,
            recency_half_life_hours=self.config.recency_half_life_hours,
        )

        # 6. fill token budget greedily from top scores
        chunks, decisions, tokens_used = _fill_budget(scored, decisions, budget)

        return AssembledContext(
            query=query,
            current_file=current_file,
            chunks=chunks,
            decisions=decisions,
            token_budget=budget,
            tokens_used=tokens_used,
            assembly_ms=(time.perf_counter() - started) * 1000,
            profile=prof.name,
        )


def _fill_budget(
    scored: list[ScoredChunk],
    decisions: list[Memory],
    token_budget: int,
) -> tuple[list[ScoredChunk], list[Memory], int]:
    decision_budget = int(token_budget * DECISION_BUDGET_FRACTION)
    kept_decisions: list[Memory] = []
    decision_tokens = 0
    for memory in decisions:
        cost = estimate_tokens(memory.content) + 10  # formatting overhead
        if decision_tokens + cost > decision_budget:
            continue
        kept_decisions.append(memory)
        decision_tokens += cost

    chunk_budget = token_budget - decision_tokens
    kept_chunks: list[ScoredChunk] = []
    chunk_tokens = 0
    for item in scored:
        cost = item.chunk.token_estimate + 15  # header/fence overhead
        if chunk_tokens + cost > chunk_budget:
            continue  # greedy: try smaller lower-ranked chunks that still fit
        kept_chunks.append(item)
        chunk_tokens += cost

    return kept_chunks, kept_decisions, chunk_tokens + decision_tokens

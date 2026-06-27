"""Relevance ranking for context chunks.

Final score is a weighted blend of:
- semantic similarity to the query (vector cosine)
- file proximity (same file > same directory > same top-level package)
- recency (exponential decay on last modification)
- edit frequency (frequently changed files are load-bearing)
- tag boost (DECISION/FIXME comments carry "why" context)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import PurePath

from dot.memory.decay import recency_score
from dot.memory.store import StoredChunk

WEIGHTS = {
    "similarity": 0.45,
    "proximity": 0.20,
    "recency": 0.20,
    "edit_frequency": 0.10,
    "tag_boost": 0.05,
}

TAG_BOOSTS = {"DECISION": 1.0, "FIXME": 0.8, "TODO": 0.5, "HACK": 0.7, "NOTE": 0.4}


@dataclass
class ScoredChunk:
    chunk: StoredChunk
    score: float
    components: dict[str, float]


def file_proximity(current_file: str | None, chunk_file: str) -> float:
    """Proximity in [0, 1]: 1.0 same file, decaying with path distance."""
    if not current_file:
        return 0.0
    if current_file == chunk_file:
        return 1.0
    current_parts = PurePath(current_file).parts
    chunk_parts = PurePath(chunk_file).parts
    shared = 0
    for a, b in zip(current_parts[:-1], chunk_parts[:-1]):
        if a != b:
            break
        shared += 1
    max_depth = max(len(current_parts), len(chunk_parts)) - 1
    if max_depth <= 0:
        return 0.5
    same_dir = shared == len(current_parts) - 1 == len(chunk_parts) - 1
    base = shared / max_depth
    return min(1.0, 0.85 if same_dir else base * 0.7)


def edit_frequency_score(edit_count: int) -> float:
    """Log-scaled edit frequency in [0, 1)."""
    return min(1.0, math.log1p(edit_count) / math.log(50))


def tag_boost(tags: list[str]) -> float:
    return max((TAG_BOOSTS.get(tag.upper(), 0.0) for tag in tags), default=0.0)


def score_chunk(
    chunk: StoredChunk,
    current_file: str | None = None,
    recency_half_life_hours: float = 72.0,
) -> ScoredChunk:
    components = {
        "similarity": max(0.0, chunk.similarity),
        "proximity": file_proximity(current_file, chunk.file_path),
        "recency": recency_score(chunk.updated_at, recency_half_life_hours)
        if chunk.updated_at
        else 0.0,
        "edit_frequency": edit_frequency_score(chunk.edit_count),
        "tag_boost": tag_boost(chunk.tags),
    }
    score = sum(WEIGHTS[name] * value for name, value in components.items())
    return ScoredChunk(chunk=chunk, score=score, components=components)


def rank_and_deduplicate(
    chunks: list[StoredChunk],
    current_file: str | None = None,
    recency_half_life_hours: float = 72.0,
) -> list[ScoredChunk]:
    """Score chunks, drop duplicates and overlapping line ranges, sort desc.

    Chunks gathered through multiple paths (similar + proximate + recent)
    keep the best similarity seen for them.
    """
    best_by_id: dict[str, StoredChunk] = {}
    for chunk in chunks:
        existing = best_by_id.get(chunk.chunk_id)
        if existing is None or chunk.similarity > existing.similarity:
            best_by_id[chunk.chunk_id] = chunk

    scored = [
        score_chunk(chunk, current_file, recency_half_life_hours)
        for chunk in best_by_id.values()
    ]
    scored.sort(key=lambda item: item.score, reverse=True)

    # Drop chunks whose line range is already covered by a higher-ranked
    # chunk from the same file (e.g. a method inside an included class).
    kept: list[ScoredChunk] = []
    covered: dict[str, list[tuple[int, int]]] = {}
    for item in scored:
        chunk = item.chunk
        ranges = covered.setdefault(chunk.file_path, [])
        overlaps = any(
            chunk.start_line >= start and chunk.end_line <= end for start, end in ranges
        )
        if overlaps:
            continue
        ranges.append((chunk.start_line, chunk.end_line))
        kept.append(item)
    return kept

"""Memory relevance decay — the forgetting curve.

Memories lose weight exponentially with age (half-life configurable per
project), but every access reinforces them, mimicking spaced repetition:
a decision someone keeps pulling into context clearly still matters.

effective_weight = confidence * 2^(-age/half_life) * (1 + ln(1 + accesses) * 0.25)

Memories whose effective weight drops below ``FORGET_THRESHOLD`` are
candidates for pruning (Dot archives rather than hard-deletes them).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

FORGET_THRESHOLD = 0.05
ACCESS_REINFORCEMENT = 0.25


def decayed_weight(
    created_at: datetime,
    confidence: float = 1.0,
    half_life_days: float = 30.0,
    access_count: int = 0,
    now: datetime | None = None,
) -> float:
    """Effective weight of a memory right now, in [0, ~confidence*2]."""
    now = now or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400)
    decay = 2 ** (-age_days / max(half_life_days, 0.01))
    reinforcement = 1.0 + math.log1p(access_count) * ACCESS_REINFORCEMENT
    return confidence * decay * reinforcement


def is_forgettable(weight: float) -> bool:
    return weight < FORGET_THRESHOLD


def recency_score(last_modified: datetime, half_life_hours: float = 72.0,
                  now: datetime | None = None) -> float:
    """Recency score in (0, 1] for code chunks — recent edits matter more."""
    now = now or datetime.now(UTC)
    if last_modified.tzinfo is None:
        last_modified = last_modified.replace(tzinfo=UTC)
    age_hours = max(0.0, (now - last_modified).total_seconds() / 3600)
    return 2 ** (-age_hours / max(half_life_hours, 0.01))

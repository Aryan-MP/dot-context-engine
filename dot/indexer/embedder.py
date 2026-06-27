"""Local embedding generation.

Uses sentence-transformers (all-MiniLM-L6-v2 by default) when installed —
fully local, no API calls. Falls back to a deterministic feature-hashing
embedder so Dot remains functional (and testable) without the ML stack.

Embeddings are cached in-process by content hash and computed in batches.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading

logger = logging.getLogger(__name__)

HASH_DIM = 384  # match MiniLM's dimensionality so stores are interchangeable
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|\d+")


def _hash_embed(text: str, dim: int = HASH_DIM) -> list[float]:
    """Deterministic feature-hashing embedding (bag of identifiers).

    Nowhere near as good as a learned model, but it preserves lexical
    similarity, needs zero dependencies, and is instant.
    """
    vector = [0.0] * dim
    tokens = _TOKEN_RE.findall(text.lower())
    for token in tokens:
        digest = hashlib.md5(token.encode()).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot_product / (norm_a * norm_b)


class Embedder:
    """Batched, cached, local embedding generation."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", batch_size: int = 64) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None
        self._model_failed = False
        self._cache: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @property
    def backend(self) -> str:
        if self._model is not None:
            return f"sentence-transformers/{self.model_name}"
        return "feature-hashing (install dot-context[ml] for semantic embeddings)"

    def _load_model(self):
        if self._model is not None or self._model_failed:
            return self._model
        with self._lock:
            if self._model is not None or self._model_failed:
                return self._model
            try:
                from sentence_transformers import (
                    SentenceTransformer,  # type: ignore[import-not-found]
                )

                logger.info("loading embedding model %s", self.model_name)
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                logger.info("sentence-transformers not installed; using hash embedder")
                self._model_failed = True
            except Exception:
                logger.exception("failed to load %s; using hash embedder", self.model_name)
                self._model_failed = True
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, using the cache where possible."""
        results: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str]] = []
        for index, text in enumerate(texts):
            key = hashlib.sha256(text.encode()).hexdigest()
            cached = self._cache.get(key)
            if cached is not None:
                results[index] = cached
            else:
                missing.append((index, text))

        if missing:
            model = self._load_model()
            missing_texts = [text for _, text in missing]
            if model is not None:
                vectors = []
                for start in range(0, len(missing_texts), self.batch_size):
                    batch = missing_texts[start : start + self.batch_size]
                    encoded = model.encode(batch, show_progress_bar=False, normalize_embeddings=True)
                    vectors.extend(vector.tolist() for vector in encoded)
            else:
                vectors = [_hash_embed(text) for text in missing_texts]

            for (index, text), vector in zip(missing, vectors):
                key = hashlib.sha256(text.encode()).hexdigest()
                self._cache[key] = vector
                results[index] = vector

        return [vector for vector in results if vector is not None]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

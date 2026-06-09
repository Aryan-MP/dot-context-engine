"""Hybrid storage: ChromaDB for vectors + SQLite for structured metadata.

SQLite (via SQLAlchemy) is the source of truth — chunk contents, file
records, edit counts, memories, dependency edges. ChromaDB holds the
vector index for fast similarity search. If ChromaDB isn't installed,
embeddings are stored in SQLite and searched brute-force, which is fine
up to tens of thousands of chunks.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import (
    Float,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from dot.config import ProjectConfig
from dot.indexer.chunker import Chunk
from dot.indexer.embedder import Embedder, cosine_similarity
from dot.memory.decay import decayed_weight, is_forgettable

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class ChunkRecord(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_path: Mapped[str] = mapped_column(String, index=True)
    language: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    symbol: Mapped[str] = mapped_column(String)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    docstring: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String, default="")  # comma-separated
    embedding_json: Mapped[str] = mapped_column(Text, default="")  # fallback vector store
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), index=True)


class FileRecord(Base):
    __tablename__ = "files"

    file_path: Mapped[str] = mapped_column(String, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    language: Mapped[str] = mapped_column(String(32), default="")
    edit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_indexed: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    last_modified: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), index=True)


class DependencyEdge(Base):
    __tablename__ = "dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String, index=True)
    target_module: Mapped[str] = mapped_column(String, index=True)


class MemoryRecord(Base):
    __tablename__ = "memories"

    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # decision | action_item | rejected | note | conversation
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="")  # git:<sha> | conversation | manual | comment
    file_path: Mapped[str] = mapped_column(String, default="", index=True)
    project: Mapped[str] = mapped_column(String, default="")
    tags: Mapped[str] = mapped_column(String, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[int] = mapped_column(Integer, default=0, index=True)
    embedding_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), index=True)


@dataclass
class StoredChunk:
    """A chunk plus the storage metadata ranking needs."""

    chunk_id: str
    file_path: str
    language: str
    kind: str
    symbol: str
    start_line: int
    end_line: int
    content: str
    docstring: str = ""
    tags: list[str] = field(default_factory=list)
    updated_at: datetime | None = None
    edit_count: int = 0
    similarity: float = 0.0

    @property
    def token_estimate(self) -> int:
        from dot.indexer.chunker import estimate_tokens

        return estimate_tokens(self.content)

    @classmethod
    def from_record(cls, record: ChunkRecord, edit_count: int = 0, similarity: float = 0.0) -> StoredChunk:
        return cls(
            chunk_id=record.chunk_id,
            file_path=record.file_path,
            language=record.language,
            kind=record.kind,
            symbol=record.symbol,
            start_line=record.start_line,
            end_line=record.end_line,
            content=record.content,
            docstring=record.docstring,
            tags=[tag for tag in record.tags.split(",") if tag],
            updated_at=record.updated_at,
            edit_count=edit_count,
            similarity=similarity,
        )


@dataclass
class Memory:
    memory_id: str
    kind: str
    content: str
    source: str = ""
    file_path: str = ""
    project: str = ""
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    access_count: int = 0
    created_at: datetime | None = None
    weight: float = 1.0
    similarity: float = 0.0

    @classmethod
    def from_record(cls, record: MemoryRecord, half_life_days: float = 30.0, similarity: float = 0.0) -> Memory:
        weight = decayed_weight(
            record.created_at, record.confidence, half_life_days, record.access_count
        )
        return cls(
            memory_id=record.memory_id,
            kind=record.kind,
            content=record.content,
            source=record.source,
            file_path=record.file_path,
            project=record.project,
            tags=[tag for tag in record.tags.split(",") if tag],
            confidence=record.confidence,
            access_count=record.access_count,
            created_at=record.created_at,
            weight=weight,
            similarity=similarity,
        )


class _ChromaBackend:
    """Vector search backed by a persistent local ChromaDB instance."""

    def __init__(self, config: ProjectConfig) -> None:
        import chromadb  # type: ignore[import-not-found]

        self._client = chromadb.PersistentClient(path=str(config.chroma_path))
        self.chunks = self._client.get_or_create_collection(
            "chunks", metadata={"hnsw:space": "cosine"}
        )
        self.memories = self._client.get_or_create_collection(
            "memories", metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, collection: str, ids: list[str], embeddings: list[list[float]]) -> None:
        getattr(self, collection).upsert(ids=ids, embeddings=embeddings)

    def delete(self, collection: str, ids: list[str]) -> None:
        if ids:
            getattr(self, collection).delete(ids=ids)

    def query(self, collection: str, embedding: list[float], n_results: int) -> list[tuple[str, float]]:
        coll = getattr(self, collection)
        count = coll.count()
        if count == 0:
            return []
        result = coll.query(query_embeddings=[embedding], n_results=min(n_results, count))
        ids = result["ids"][0]
        distances = result["distances"][0]
        return [(chunk_id, 1.0 - distance) for chunk_id, distance in zip(ids, distances)]


class Store:
    """Unified storage facade: chunks, memories, files, dependency graph."""

    def __init__(self, config: ProjectConfig, embedder: Embedder | None = None) -> None:
        self.config = config
        self.embedder = embedder or Embedder(config.embedding_model)
        config.dot_dir.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{config.db_path}", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)

        self._chroma: _ChromaBackend | None = None
        try:
            self._chroma = _ChromaBackend(config)
            logger.info("vector backend: chromadb at %s", config.chroma_path)
        except ImportError:
            logger.info("chromadb not installed; using SQLite brute-force vector search")
        except Exception:
            logger.exception("chromadb init failed; falling back to SQLite vectors")

    def session(self) -> Session:
        return Session(self.engine)

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------
    def upsert_chunks(self, chunks: list[Chunk], content_hash: str = "") -> int:
        """Replace all chunks for the files covered, embed, and store."""
        if not chunks:
            return 0
        embeddings = self.embedder.embed([chunk.embedding_text() for chunk in chunks])
        now = datetime.now(UTC)
        file_paths = {chunk.file_path for chunk in chunks}

        with self.session() as session:
            old_ids = session.scalars(
                select(ChunkRecord.chunk_id).where(ChunkRecord.file_path.in_(file_paths))
            ).all()
            session.execute(delete(ChunkRecord).where(ChunkRecord.file_path.in_(file_paths)))
            session.execute(
                delete(DependencyEdge).where(DependencyEdge.source_file.in_(file_paths))
            )

            seen_edges: set[tuple[str, str]] = set()
            for chunk, embedding in zip(chunks, embeddings):
                session.add(
                    ChunkRecord(
                        chunk_id=chunk.chunk_id,
                        file_path=chunk.file_path,
                        language=chunk.language,
                        kind=chunk.kind,
                        symbol=chunk.symbol,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        content=chunk.content,
                        docstring=chunk.docstring,
                        tags=",".join(chunk.tags),
                        embedding_json="" if self._chroma else json.dumps(embedding),
                        created_at=now,
                        updated_at=now,
                    )
                )
                for module in chunk.imports:
                    edge = (chunk.file_path, module)
                    if edge not in seen_edges:
                        seen_edges.add(edge)
                        session.add(DependencyEdge(source_file=chunk.file_path, target_module=module))

            for file_path in file_paths:
                record = session.get(FileRecord, file_path)
                language = next(c.language for c in chunks if c.file_path == file_path)
                if record is None:
                    session.add(
                        FileRecord(
                            file_path=file_path, content_hash=content_hash, language=language,
                            edit_count=1, last_indexed=now, last_modified=now,
                        )
                    )
                else:
                    record.content_hash = content_hash
                    record.edit_count += 1
                    record.last_indexed = now
                    record.last_modified = now
            session.commit()

        if self._chroma:
            self._chroma.delete("chunks", list(old_ids))
            self._chroma.upsert("chunks", [chunk.chunk_id for chunk in chunks], embeddings)
        return len(chunks)

    def delete_file(self, file_path: str) -> None:
        with self.session() as session:
            old_ids = session.scalars(
                select(ChunkRecord.chunk_id).where(ChunkRecord.file_path == file_path)
            ).all()
            session.execute(delete(ChunkRecord).where(ChunkRecord.file_path == file_path))
            session.execute(delete(DependencyEdge).where(DependencyEdge.source_file == file_path))
            session.execute(delete(FileRecord).where(FileRecord.file_path == file_path))
            session.commit()
        if self._chroma:
            self._chroma.delete("chunks", list(old_ids))

    def file_hash(self, file_path: str) -> str | None:
        with self.session() as session:
            record = session.get(FileRecord, file_path)
            return record.content_hash if record else None

    def query_chunks(self, query: str, n_results: int = 20) -> list[StoredChunk]:
        """Vector similarity search over code chunks."""
        embedding = self.embedder.embed_one(query)
        if self._chroma:
            hits = self._chroma.query("chunks", embedding, n_results)
        else:
            hits = self._brute_force(ChunkRecord, embedding, n_results)
        return self._hydrate_chunks(hits)

    def _brute_force(self, model, embedding: list[float], n_results: int) -> list[tuple[str, float]]:  # noqa: ANN001
        id_column = "chunk_id" if model is ChunkRecord else "memory_id"
        with self.session() as session:
            rows = session.execute(
                select(getattr(model, id_column), model.embedding_json).where(
                    model.embedding_json != ""
                )
            ).all()
        scored = [
            (row_id, cosine_similarity(embedding, json.loads(vector_json)))
            for row_id, vector_json in rows
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:n_results]

    def _hydrate_chunks(self, hits: list[tuple[str, float]]) -> list[StoredChunk]:
        if not hits:
            return []
        similarity_by_id = dict(hits)
        with self.session() as session:
            records = session.scalars(
                select(ChunkRecord).where(ChunkRecord.chunk_id.in_(similarity_by_id))
            ).all()
            edit_counts = self._edit_counts(session, {record.file_path for record in records})
            chunks = [
                StoredChunk.from_record(
                    record,
                    edit_count=edit_counts.get(record.file_path, 0),
                    similarity=similarity_by_id.get(record.chunk_id, 0.0),
                )
                for record in records
            ]
        chunks.sort(key=lambda chunk: chunk.similarity, reverse=True)
        return chunks

    @staticmethod
    def _edit_counts(session: Session, file_paths: set[str]) -> dict[str, int]:
        if not file_paths:
            return {}
        rows = session.execute(
            select(FileRecord.file_path, FileRecord.edit_count).where(
                FileRecord.file_path.in_(file_paths)
            )
        ).all()
        return dict(rows)

    def get_chunks_for_file(self, file_path: str) -> list[StoredChunk]:
        with self.session() as session:
            records = session.scalars(
                select(ChunkRecord)
                .where(ChunkRecord.file_path == file_path)
                .order_by(ChunkRecord.start_line)
            ).all()
            edit_counts = self._edit_counts(session, {file_path})
            return [
                StoredChunk.from_record(record, edit_counts.get(file_path, 0))
                for record in records
            ]

    def get_proximate_chunks(self, current_file: str, n: int = 10) -> list[StoredChunk]:
        """Chunks from the same directory/module as the current file."""
        from pathlib import PurePath

        directory = str(PurePath(current_file).parent)
        with self.session() as session:
            records = session.scalars(
                select(ChunkRecord)
                .where(ChunkRecord.file_path.like(f"{directory}%"))
                .where(ChunkRecord.file_path != current_file)
                .order_by(ChunkRecord.updated_at.desc())
                .limit(n)
            ).all()
            edit_counts = self._edit_counts(session, {record.file_path for record in records})
            return [
                StoredChunk.from_record(record, edit_counts.get(record.file_path, 0))
                for record in records
            ]

    def get_recent_chunks(self, hours: float = 24.0, n: int = 10) -> list[StoredChunk]:
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        with self.session() as session:
            records = session.scalars(
                select(ChunkRecord)
                .where(ChunkRecord.updated_at >= cutoff.replace(tzinfo=None))
                .order_by(ChunkRecord.updated_at.desc())
                .limit(n)
            ).all()
            edit_counts = self._edit_counts(session, {record.file_path for record in records})
            return [
                StoredChunk.from_record(record, edit_counts.get(record.file_path, 0))
                for record in records
            ]

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------
    def add_memory(
        self,
        content: str,
        kind: str = "note",
        source: str = "manual",
        file_path: str = "",
        tags: list[str] | None = None,
        confidence: float = 1.0,
        created_at: datetime | None = None,
        memory_id: str | None = None,
    ) -> Memory:
        memory_id = memory_id or str(uuid.uuid4())
        embedding = self.embedder.embed_one(content)
        record = MemoryRecord(
            memory_id=memory_id,
            kind=kind,
            content=content,
            source=source,
            file_path=file_path,
            project=self.config.project_name,
            tags=",".join(tags or []),
            confidence=confidence,
            access_count=0,
            archived=0,
            embedding_json="" if self._chroma else json.dumps(embedding),
            created_at=created_at or datetime.now(UTC),
        )
        with self.session() as session:
            session.merge(record)
            session.commit()
        if self._chroma:
            self._chroma.upsert("memories", [memory_id], [embedding])
        return Memory.from_record(record, self.config.memory_half_life_days)

    def query_memories(self, query: str, n: int = 5) -> list[Memory]:
        embedding = self.embedder.embed_one(query)
        if self._chroma:
            hits = self._chroma.query("memories", embedding, n * 3)
        else:
            hits = self._brute_force(MemoryRecord, embedding, n * 3)
        similarity_by_id = dict(hits)
        with self.session() as session:
            records = session.scalars(
                select(MemoryRecord)
                .where(MemoryRecord.memory_id.in_(similarity_by_id))
                .where(MemoryRecord.archived == 0)
            ).all()
            memories = [
                Memory.from_record(
                    record, self.config.memory_half_life_days,
                    similarity=similarity_by_id.get(record.memory_id, 0.0),
                )
                for record in records
            ]
            # mark access — reinforcement against decay
            for record in records:
                record.access_count += 1
            session.commit()
        memories.sort(key=lambda memory: memory.similarity * (0.5 + 0.5 * memory.weight), reverse=True)
        return memories[:n]

    def list_memories(self, kind: str | None = None, limit: int = 100, include_archived: bool = False) -> list[Memory]:
        with self.session() as session:
            stmt = select(MemoryRecord).order_by(MemoryRecord.created_at.desc()).limit(limit)
            if kind:
                stmt = stmt.where(MemoryRecord.kind == kind)
            if not include_archived:
                stmt = stmt.where(MemoryRecord.archived == 0)
            return [
                Memory.from_record(record, self.config.memory_half_life_days)
                for record in session.scalars(stmt).all()
            ]

    def delete_memory(self, memory_id: str) -> bool:
        with self.session() as session:
            record = session.get(MemoryRecord, memory_id)
            if record is None:
                return False
            session.delete(record)
            session.commit()
        if self._chroma:
            self._chroma.delete("memories", [memory_id])
        return True

    def forget_pattern(self, pattern: str) -> int:
        """Delete all memories whose content matches a regex/substring pattern."""
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            matcher = compiled.search
        except re.error:
            lowered = pattern.lower()
            matcher = lambda text: lowered in text.lower()  # noqa: E731
        removed = 0
        with self.session() as session:
            records = session.scalars(select(MemoryRecord)).all()
            doomed = [record for record in records if matcher(record.content)]
            for record in doomed:
                session.delete(record)
                removed += 1
            session.commit()
        if self._chroma and doomed:
            self._chroma.delete("memories", [record.memory_id for record in doomed])
        return removed

    def prune_decayed(self) -> int:
        """Archive memories whose decayed weight fell below the threshold."""
        archived = 0
        with self.session() as session:
            records = session.scalars(
                select(MemoryRecord).where(MemoryRecord.archived == 0)
            ).all()
            for record in records:
                weight = decayed_weight(
                    record.created_at, record.confidence,
                    self.config.memory_half_life_days, record.access_count,
                )
                if is_forgettable(weight):
                    record.archived = 1
                    archived += 1
            session.commit()
        return archived

    def export_memories(self) -> list[dict]:
        """All memories as portable JSON-serializable dicts."""
        memories = self.list_memories(limit=100_000, include_archived=True)
        return [
            {
                "id": memory.memory_id,
                "kind": memory.kind,
                "content": memory.content,
                "source": memory.source,
                "file_path": memory.file_path,
                "project": memory.project,
                "tags": memory.tags,
                "confidence": memory.confidence,
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
                "weight": round(memory.weight, 4),
            }
            for memory in memories
        ]

    # ------------------------------------------------------------------
    # Graph + stats
    # ------------------------------------------------------------------
    def dependency_graph(self) -> dict:
        """Dependency graph as {nodes: [...], edges: [...]} JSON."""
        with self.session() as session:
            files = session.scalars(select(FileRecord)).all()
            edges = session.scalars(select(DependencyEdge)).all()
        nodes = [
            {
                "id": record.file_path,
                "language": record.language,
                "edit_count": record.edit_count,
                "last_modified": record.last_modified.isoformat(),
            }
            for record in files
        ]
        # Resolve import targets to project files where possible.
        path_index = {record.file_path for record in files}
        resolved_edges = []
        for edge in edges:
            target = _resolve_module_to_file(edge.target_module, path_index)
            resolved_edges.append(
                {
                    "source": edge.source_file,
                    "target": target or edge.target_module,
                    "internal": target is not None,
                }
            )
        return {"nodes": nodes, "edges": resolved_edges}

    def stats(self) -> dict:
        with self.session() as session:
            chunk_count = session.scalar(select(func.count()).select_from(ChunkRecord)) or 0
            file_count = session.scalar(select(func.count()).select_from(FileRecord)) or 0
            memory_count = session.scalar(
                select(func.count()).select_from(MemoryRecord).where(MemoryRecord.archived == 0)
            ) or 0
            last_indexed = session.scalar(select(func.max(FileRecord.last_indexed)))
        return {
            "project": self.config.project_name,
            "project_root": self.config.project_root,
            "files_indexed": file_count,
            "chunks": chunk_count,
            "memories": memory_count,
            "last_indexed": last_indexed.isoformat() if last_indexed else None,
            "embedding_backend": self.embedder.backend,
            "vector_backend": "chromadb" if self._chroma else "sqlite",
        }


def _resolve_module_to_file(module: str, file_paths: set[str]) -> str | None:
    """Best-effort: map an import like 'dot.indexer.parser' to a project file."""
    candidate = module.replace(".", "/").replace("::", "/").strip("./")
    if not candidate:
        return None
    for path in file_paths:
        normalized = path.replace("\\", "/")
        stem = normalized.rsplit(".", 1)[0]
        if stem.endswith(candidate) or stem.endswith(candidate + "/__init__"):
            return path
    return None

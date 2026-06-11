"""Git-native shared team memory.

Shared memories live in ``dot-memories.jsonl`` at the project root — a
committed, append-only file that travels with the repository. Because every
memory has a stable id and imports are idempotent, the workflow is simply:

    teammate A:  dot memory add "Chose X over Y because…" --share
                 git commit + push
    teammate B:  git pull        →  daemon notices the file changed and
                                    imports the new memories automatically

Append-only + content-addressed ids means git merges are conflict-free in
practice, and re-importing the whole file is always safe.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from dot.config import ProjectConfig
from dot.memory.store import Memory, Store

logger = logging.getLogger(__name__)


def _author(project_root: str) -> str:
    """Best-effort author identity: git config user.name, else OS user."""
    try:
        import git

        reader = git.Repo(project_root, search_parent_directories=True).config_reader()
        name = reader.get_value("user", "name", default="") or ""
        if name:
            return str(name)
    except Exception:
        pass
    import getpass

    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def memory_to_record(memory: Memory, author: str) -> dict:
    return {
        "id": memory.memory_id,
        "kind": memory.kind,
        "content": memory.content,
        "source": memory.source,
        "file_path": memory.file_path,
        "tags": memory.tags,
        "confidence": memory.confidence,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "author": author,
    }


def export_memory(config: ProjectConfig, memory: Memory) -> bool:
    """Append a memory to the shared file. Returns False if already shared."""
    path = config.shared_memories_path
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("id") == memory.memory_id:
                    return False
            except json.JSONDecodeError:
                continue
    record = memory_to_record(memory, _author(config.project_root))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("shared memory %s to %s", memory.memory_id[:8], path.name)
    return True


def import_shared(store: Store, config: ProjectConfig | None = None) -> int:
    """Import any shared memories not yet in the local store. Idempotent."""
    config = config or store.config
    path = config.shared_memories_path
    if not path.exists():
        return 0
    records = _parse_jsonl(path)
    return import_records(store, records)


def import_file(store: Store, path) -> int:
    """Import memories from an exported file (.json from `dot memory export`
    or a .jsonl shared-memories file). Idempotent."""
    from pathlib import Path

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".jsonl":
        records = _parse_jsonl(path)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("memories", data) if isinstance(data, dict) else data
        if not isinstance(records, list):
            raise ValueError(f"{path.name}: expected a list of memories")
    return import_records(store, records)


def _parse_jsonl(path) -> list[dict]:
    records: list[dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("%s:%d is not valid JSON; skipping", path.name, line_no)
    return records


def import_records(store: Store, records: list[dict]) -> int:
    """Idempotently add memory records to the local store."""
    existing = store.existing_memory_ids()
    imported = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        memory_id = record.get("id")
        content = (record.get("content") or "").strip()
        if not memory_id or not content or memory_id in existing:
            continue

        created_at = None
        if record.get("created_at"):
            try:
                created_at = datetime.fromisoformat(record["created_at"])
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
            except ValueError:
                pass

        tags = list(record.get("tags") or [])
        author = record.get("author")
        if author and f"author:{author}" not in tags:
            tags.append(f"author:{author}")
        if "shared" not in tags:
            tags.append("shared")

        store.add_memory(
            content=content,
            kind=record.get("kind", "note"),
            source=record.get("source") or "shared",
            file_path=record.get("file_path", ""),
            tags=tags,
            confidence=float(record.get("confidence", 1.0)),
            created_at=created_at,
            memory_id=memory_id,
        )
        existing.add(memory_id)
        imported += 1

    if imported:
        logger.info("imported %d memories", imported)
    return imported

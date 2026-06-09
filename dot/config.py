"""Project + global configuration for Dot.

Dot keeps a global home directory (``~/.dot``) for daemon state and a
per-project ``.dot/`` directory holding that project's index, memories,
and settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

DOT_DIR_NAME = ".dot"
CONFIG_FILE_NAME = "config.json"

IGNORED_DIRS = {
    ".git", ".dot", ".hg", ".svn", "node_modules", "__pycache__", ".venv",
    "venv", ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache", "dist",
    "build", ".next", ".cache", "target", ".idea", ".vscode",
}

INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".scala",
    ".sh", ".sql", ".md", ".toml", ".yaml", ".yml",
}


def dot_home() -> Path:
    """Global Dot home directory (override with DOT_HOME)."""
    home = os.environ.get("DOT_HOME")
    path = Path(home) if home else Path.home() / ".dot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward from ``start`` looking for a .dot/ or .git/ directory."""
    current = (start or Path.cwd()).resolve()
    fallback = None
    for candidate in [current, *current.parents]:
        if (candidate / DOT_DIR_NAME).is_dir():
            return candidate
        if fallback is None and (candidate / ".git").is_dir():
            fallback = candidate
    return fallback


@dataclass
class ProjectConfig:
    """Per-project settings, persisted to .dot/config.json."""

    project_root: str
    project_name: str = ""
    embedding_model: str = "all-MiniLM-L6-v2"
    token_budget: int = 4000
    recency_half_life_hours: float = 72.0
    memory_half_life_days: float = 30.0
    api_host: str = "127.0.0.1"
    api_port: int = 7337
    extra_ignored_dirs: list[str] = field(default_factory=list)
    profiles: dict[str, dict] = field(
        default_factory=lambda: {
            "quick-assist": {"token_budget": 2000, "n_chunks": 8, "include_decisions": True},
            "deep-dive": {"token_budget": 8000, "n_chunks": 30, "include_decisions": True},
        }
    )

    def __post_init__(self) -> None:
        if not self.project_name:
            self.project_name = Path(self.project_root).name

    @property
    def dot_dir(self) -> Path:
        return Path(self.project_root) / DOT_DIR_NAME

    @property
    def db_path(self) -> Path:
        return self.dot_dir / "dot.sqlite3"

    @property
    def chroma_path(self) -> Path:
        return self.dot_dir / "chroma"

    @property
    def ignored_dirs(self) -> set[str]:
        return IGNORED_DIRS | set(self.extra_ignored_dirs)

    def save(self) -> None:
        self.dot_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.dot_dir / CONFIG_FILE_NAME
        config_path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, project_root: Path) -> ProjectConfig:
        config_path = Path(project_root) / DOT_DIR_NAME / CONFIG_FILE_NAME
        if config_path.exists():
            data = json.loads(config_path.read_text())
            data["project_root"] = str(project_root)
            known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            return cls(**{k: v for k, v in data.items() if k in known})
        return cls(project_root=str(project_root))

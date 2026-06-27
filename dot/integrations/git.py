"""Deep git history integration.

Beyond decision mining (see dot.memory.decisions), this module exposes:
- recent activity (commits, branches) for recency-aware ranking
- per-file churn and blame summaries used by the ranker
- a hook installer so every new commit is captured live
"""

from __future__ import annotations

import logging
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

POST_COMMIT_HOOK = """#!/bin/sh
# Installed by `dot init` — notifies the Dot daemon of new commits.
# Safe to remove; Dot also picks up commits on its periodic git scan.
curl -s -X POST http://127.0.0.1:7337/hooks/git/commit -m 2 >/dev/null 2>&1 || true
"""


@dataclass
class CommitInfo:
    sha: str
    author: str
    message: str
    committed_at: datetime
    files: list[str]


@dataclass
class FileGitStats:
    file_path: str
    commit_count: int
    last_author: str
    last_committed_at: datetime | None
    recent_authors: list[str]


class GitIntegration:
    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self._repo = None
        self._unavailable = False

    @property
    def repo(self):
        if self._repo is not None or self._unavailable:
            return self._repo
        try:
            import git

            self._repo = git.Repo(self.project_root, search_parent_directories=True)
        except Exception:
            self._unavailable = True
            logger.debug("git unavailable for %s", self.project_root)
        return self._repo

    @property
    def available(self) -> bool:
        return self.repo is not None

    def current_branch(self) -> str | None:
        repo = self.repo
        if repo is None:
            return None
        try:
            return repo.active_branch.name
        except Exception:
            return None  # detached HEAD

    def recent_commits(self, max_count: int = 50) -> list[CommitInfo]:
        repo = self.repo
        if repo is None:
            return []
        commits: list[CommitInfo] = []
        try:
            for commit in repo.iter_commits(max_count=max_count):
                message = commit.message if isinstance(commit.message, str) else ""
                commits.append(
                    CommitInfo(
                        sha=commit.hexsha,
                        author=str(commit.author.name),
                        message=message.strip(),
                        committed_at=datetime.fromtimestamp(commit.committed_date, tz=UTC),
                        files=list(commit.stats.files)[:50],
                    )
                )
        except Exception:
            logger.exception("failed reading git log")
        return commits

    def file_stats(self, file_path: str, max_commits: int = 100) -> FileGitStats | None:
        """Churn + blame summary for one file (who touched it, how often)."""
        repo = self.repo
        if repo is None:
            return None
        try:
            relative = str(Path(file_path).resolve().relative_to(Path(repo.working_dir).resolve()))
        except ValueError:
            relative = file_path
        try:
            commits = list(repo.iter_commits(paths=relative, max_count=max_commits))
        except Exception:
            return None
        if not commits:
            return None
        authors: list[str] = []
        for commit in commits[:10]:
            name = str(commit.author.name)
            if name not in authors:
                authors.append(name)
        return FileGitStats(
            file_path=file_path,
            commit_count=len(commits),
            last_author=str(commits[0].author.name),
            last_committed_at=datetime.fromtimestamp(commits[0].committed_date, tz=UTC),
            recent_authors=authors,
        )

    def changed_files_since(self, ref: str = "HEAD~10") -> list[str]:
        repo = self.repo
        if repo is None:
            return []
        try:
            diff = repo.git.diff("--name-only", ref, "HEAD")
            return [line for line in diff.splitlines() if line.strip()]
        except Exception:
            return []

    def install_post_commit_hook(self) -> bool:
        """Install a post-commit hook that pings the daemon. Idempotent."""
        repo = self.repo
        if repo is None:
            return False
        hooks_dir = Path(repo.git_dir) / "hooks"
        hook_path = hooks_dir / "post-commit"
        if hook_path.exists() and "Dot daemon" not in hook_path.read_text(errors="replace"):
            logger.info("post-commit hook exists and isn't ours; leaving it alone")
            return False
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(POST_COMMIT_HOOK)
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        return True

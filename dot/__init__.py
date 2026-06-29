"""Dot — a local-first AI context memory daemon.

Dot watches your codebase, indexes it semantically, captures architectural
decisions, and serves the right context to any AI tool via a local REST API.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the installed package metadata (pyproject.toml).
    __version__ = version("dot-context")
except PackageNotFoundError:
    # Running from a source tree that was never installed (e.g. tests on a
    # fresh checkout). Keep in sync with pyproject.toml as a fallback only.
    __version__ = "0.1.0a2"

DEFAULT_PORT = 7337
DEFAULT_HOST = "127.0.0.1"

---
layout: ../../layouts/DocsLayout.astro
title: Installation
description: Install Dot from PyPI or from source, choose the right extras, and verify it works.
---

Dot needs **Python 3.11 or newer**. Pick the install that fits you.

## From PyPI (recommended)

```bash
pip install dot-context[ml]
dot version
```

The `[ml]` extra pulls in ChromaDB and sentence-transformers so Dot can do real
semantic search. The first time you index a project it downloads the
`all-MiniLM-L6-v2` model (about 90 MB) from Hugging Face. After that, everything
runs offline.

### Light build (no ML stack)

```bash
pip install dot-context
```

Without `[ml]`, Dot falls back to a deterministic hashing embedder and SQLite
vector search. It still works, but it matches on shared words rather than
meaning. Fine for a first look; install the `[ml]` extra when you want the real
thing.

## From source

```bash
git clone https://github.com/Aryan-MP/dot-context-engine.git
cd dot-context-engine
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Optional extras

| Extra | Adds | When you want it |
|---|---|---|
| `ml` | ChromaDB + sentence-transformers | Real semantic search (recommended) |
| `treesitter` | Tree-sitter grammars | Precise parsing for 30+ languages |
| `dev` | pytest, ruff | Contributing or running the test suite |

Combine them: `pip install "dot-context[ml,treesitter]"`.

## Verify your install

```bash
dot version      # prints the installed version
dot doctor       # checks Python, optional deps, ports, git, and writability
```

`dot doctor` is the fastest way to see exactly what is and isn't set up. It
reports each check as ok, a warning, or a failure, so you know what to fix
before indexing anything.

## Platform notes

Dot runs on **macOS, Linux, and Windows**. The background daemon installs as a
`launchd` agent on macOS and a `systemd` user unit on Linux via
`dot daemon install-service`; on Windows, run `dot daemon start` (for example
from Task Scheduler) to keep it alive.

Next: **[Quick start](/docs/quickstart)**.

# ● Dot

[![PyPI](https://img.shields.io/pypi/v/dot-context?color=blue&label=PyPI)](https://pypi.org/project/dot-context/)
[![GitHub release](https://img.shields.io/github/v/release/Aryan-MP/dot-context-engine?include_prereleases&label=release)](https://github.com/Aryan-MP/dot-context-engine/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/Aryan-MP/dot-context-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/Aryan-MP/dot-context-engine/actions/workflows/ci.yml)

**A local-first AI context memory daemon.** Stop re-explaining your codebase to every AI tool.

Every AI tool starts from zero: you explain your architecture to Claude Code, then again
to Copilot, then again in a new chat. Dot ends that. It runs silently in the background,
builds a deep understanding of your codebase and the decisions behind it, and serves the
right context to any AI tool through a local REST API.

**Local. Private. Model-agnostic. Open source.** No code leaves your machine - embeddings
are generated locally with sentence-transformers, storage is SQLite + ChromaDB on disk.

## Install

```bash
pip install dot-context[ml]        # alpha release from PyPI, with local embeddings
dot --version
```

Or install the light build (no ML stack - uses deterministic hashing instead):

```bash
pip install dot-context
```

For development, clone and install in editable mode:

```bash
git clone https://github.com/Aryan-MP/dot-context-engine.git
cd dot-context-engine && pip install -e ".[dev]"
```

- **dot-indexer** chunks code by function/class (not fixed token windows), extracts
  docstrings, imports, and TODO/`decided to…` comments, and embeds everything locally.
- **dot-memory** mines architectural decisions from commit messages and conversations,
  with a forgetting curve - stale memories decay, frequently used ones are reinforced.
- **dot-context** assembles context ranked by semantic similarity, file proximity,
  recency, and edit frequency, fills a token budget greedily, and formats it for the
  consumer (Claude XML, concise Copilot, markdown, or raw JSON).

## Quick start

```bash
cd your-project
dot init                          # index the project, wire up git + Claude Code hooks
dot daemon start                  # keep watching in the background

dot ask "how does auth middleware work?"
dot inject "refactoring the billing module" --fmt claude | pbcopy
dot status
dot dashboard                     # web UI at http://localhost:7337/ui
```

## See it in action

![Dot CLI workflow demo](docs/assets/screenshots/demo.gif)

| `dot status` | `dot dashboard` | VS Code extension |
|---|---|---|
| ![CLI status](docs/assets/screenshots/screenshot-cli.png) | ![Dashboard](docs/assets/screenshots/screenshot-dashboard.png) | ![Extension](docs/assets/screenshots/screenshot-extension.png) |


Full walkthrough with experiments: [docs/getting-started.md](docs/getting-started.md)  
Deep technical internals: [docs/internals.md](docs/internals.md)  
Prerequisites from zero: [docs/foundations.md](docs/foundations.md)

## CLI

| command | what it does |
|---|---|
| `dot init` | initialize Dot in a project (+ git hook, CLAUDE.md, Claude Code hook) |
| `dot status` | what Dot knows about the current project |
| `dot ask "…"` | query your codebase in natural language |
| `dot inject [query]` | print assembled context - pipe it anywhere |
| `dot memory list/add/export/delete` | browse and manage captured decisions |
| `dot sync` | force re-index |
| `dot forget "pattern"` | remove memories matching a pattern |
| `dot dashboard` | open the web UI |
| `dot daemon run/start/stop/install-service` | control the daemon (launchd/systemd) |

## REST API (localhost:7337)

```
GET  /status                 daemon health + project stats
GET  /context?query=&file=&fmt=claude|copilot|markdown|raw
POST /memory                 capture a decision        GET /memory   browse
POST /memory/conversation    extract decisions from an AI transcript
DELETE /memory/{id}          forget
GET  /graph                  dependency graph JSON
POST /ask                    natural-language codebase query
POST /sync                   force re-index
```

## Integrations

- **Claude Code** - `dot init` adds a CLAUDE.md section and a SessionStart hook that
  injects context at the start of every session.
- **VS Code / Copilot** - the [extension](vscode-extension/) shows "what Dot knows about
  this file" in a sidebar, registers Dot as a Language Model tool for Copilot Chat
  (`#dotContext`), and offers one-click decision capture. Download the `.vsix` from the
  [latest release](https://github.com/Aryan-MP/dot-context-engine/releases/latest).
- **Anything else** - `curl localhost:7337/context?query=...&fmt=raw`.

## Development

```bash
make install     # editable install with dev extras
make test        # pytest
make lint        # ruff
make dashboard   # build the web UI into dashboard/dist (served at /ui)
make extension   # compile the VS Code extension
```

The ML stack (`chromadb`, `sentence-transformers`) and tree-sitter are **optional
extras** - without them Dot degrades to a deterministic hashing embedder, SQLite
brute-force vector search, and heuristic parsing, so the full pipeline still works
(and tests run) on any machine.

See [docs/getting-started.md](docs/getting-started.md) for the full
walkthrough and test experiments, [docs/internals.md](docs/internals.md)
for the complete technical deep dive (architecture, algorithms, math, and
trade-offs), and [docs/integrations.md](docs/integrations.md) for tool wiring.

## Contributing

We welcome bug reports, feature ideas, and pull requests. See
[CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT

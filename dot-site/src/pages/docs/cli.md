---
layout: ../../layouts/DocsLayout.astro
title: Commands
description: The complete Dot command-line reference — every command, subcommand, and option.
---

Run `dot --help`, or `dot <command> --help`, to see any of this in your terminal.
Most commands work whether or not the background daemon is running: if it is,
they talk to it; if not, they run in-process.

## Core commands

| Command | What it does |
|---|---|
| `dot init [path]` | Initialize Dot in a project: index code, mine git decisions, install the commit hook, wire up integrations. |
| `dot status` | Show what Dot knows: files, chunks, memories, storage size, daemon state, port. |
| `dot ask "question"` | Query your codebase in natural language. |
| `dot inject [query]` | Print assembled context to stdout — pipe it into any tool. |
| `dot sync` | Re-index changed files (add `--force` for everything). |
| `dot forget "pattern"` | Remove memories matching a regex/substring. |
| `dot import [file]` | Import shared memories (from `dot-memories.jsonl`, or an exported file). |
| `dot doctor` | Run health checks and report what's wrong. |
| `dot dashboard` | Open the web UI in your browser. |
| `dot mcp` | Run the MCP server on stdio (used by Claude Code; you rarely call this directly). |
| `dot version` | Print the installed version. |

### `dot init`

```bash
dot init [PATH]
```

| Option | Default | Effect |
|---|---|---|
| `--claude / --no-claude` | auto-detect | Force or skip Claude Code wiring (CLAUDE.md, SessionStart hook, MCP registration). |
| `--copilot` | off | Maintain `.github/copilot-instructions.md` for GitHub Copilot. |
| `--conversations` | off | Opt in to capturing decisions from local Claude Code session transcripts. |
| `--sync / --no-sync` | sync | Run (or skip) the initial index. |

### `dot ask` and `dot inject`

```bash
dot ask "how does auth middleware work?" --fmt markdown
dot inject "billing refactor" --file billing/charge.py --fmt claude --budget 4000
```

| Option | Applies to | Values |
|---|---|---|
| `--fmt` | both | `claude`, `copilot`, `markdown`, `raw` |
| `--file` | both | Anchor file for proximity ranking |
| `--budget` | inject | Token budget (overrides config) |
| `--profile` | inject | A named profile, e.g. `quick-assist`, `deep-dive` |

## Memory commands

| Command | What it does |
|---|---|
| `dot memory list` | Browse captured memories. Options: `--kind`, `--query/-q`, `--limit`. |
| `dot memory add "text"` | Capture a decision. Options: `--kind`, `--file`, `--tag`, `--share`. |
| `dot memory share <id>` | Share an already-captured memory with the team. |
| `dot memory pull` | Import shared memories after a `git pull`. |
| `dot memory export` | Write all memories to portable JSON (`-o file.json`). |
| `dot memory delete <id>` | Forget a single memory by id. |

```bash
dot memory add "Decided to shard by tenant id" --kind decision --share
dot memory list -q "database" --limit 20
```

## Daemon commands

| Command | What it does |
|---|---|
| `dot daemon start` | Start the background daemon. Options: `--project`, `--port`. |
| `dot daemon stop` | Stop the background daemon. |
| `dot daemon run` | Run the daemon in the foreground (useful for debugging). |
| `dot daemon install-service` | Install a `launchd` (macOS) or `systemd` (Linux) user service. |

```bash
dot daemon start            # background, prints the pid and port
dot daemon install-service  # survive reboots
```

If the preferred port (7337) is taken, the daemon automatically uses the next
free one and records it in the project's config — `dot status` always shows the
real port.

Next: **[Configuration](/docs/configuration)**.

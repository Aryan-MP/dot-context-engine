# Getting started with Dot

A complete guide for installing Dot, wiring it into your tools, and testing
every feature with verifiable experiments. Written for someone sitting down
to evaluate the product seriously.

Dot is a local daemon that gives every AI tool a persistent memory of your
codebase: what the code is, how it connects, and why it is the way it is.
Everything runs on your machine. Nothing is uploaded anywhere.

## Contents

1. [Install](#1-install)
2. [Initialize a project](#2-initialize-a-project)
3. [The command line tour](#3-the-command-line-tour)
4. [Feature experiments (test checklist)](#4-feature-experiments)
5. [Team collaboration](#5-team-collaboration)
6. [AI tool integrations](#6-ai-tool-integrations)
7. [Configuration reference](#7-configuration-reference)
8. [Storage: how much disk does Dot use?](#8-storage)
9. [Troubleshooting](#9-troubleshooting)
10. [Uninstall / reset](#10-uninstall-reset)

---

## 1. Install

You need Python 3.11 or newer. Install from PyPI:

```bash
pip install "dot-context[ml]"     # recommended: with local embeddings
dot version                       # expect: dot 0.1.0
```

Or the light build (no ML stack - see the note below):

```bash
pip install dot-context
```

To hack on Dot itself, install from source in editable mode instead:

```bash
git clone https://github.com/Aryan-MP/dot-context-engine.git
cd dot-context-engine

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
dot version
```

### The ML extra (recommended)

The `[ml]` extra above pulls in everything below. If you started with the
light build, add it any time:

```bash
pip install "dot-context[ml]"
```

This adds ChromaDB (a local vector database) and sentence-transformers
(local embedding model). The first index downloads the all-MiniLM-L6-v2
model, about 90 MB, from HuggingFace. After that, everything is offline.

Without `[ml]`, Dot still works using a deterministic hashing embedder and
SQLite vector search. That mode matches on shared words, not meaning. It is
fine for a quick look, but semantic search is the product, so install the
extra if you can.

Optional extras:

```bash
pip install -e ".[treesitter]"   # precise AST parsing for 30+ languages
```

## 2. Initialize a project

Run init inside a project you actually work on. The experience is far more
convincing with months of real git history than with a toy folder.

```bash
cd ~/code/your-project
dot init
```

What init does, in order:

1. Creates `.dot/` (config, SQLite database, vector index) and adds `.dot/`
   to your project's `.gitignore` so the machine-local index is never
   committed.
2. Indexes every source file: parsed into functions and classes, chunked,
   embedded, stored.
3. Mines the last 500 git commits for decisions (phrases like "chose X over
   Y", "decided to", "workaround for").
4. Installs a git post-commit hook so future commits are captured live.
5. Imports `dot-memories.jsonl` if the repo contains one (shared team
   memories, see section 5).
6. Wires up Claude Code, but only if it detects Claude usage in the project
   (a `.claude/` directory, a CLAUDE.md, or a `.mcp.json`). Force it with
   `--claude`, suppress it with `--no-claude`.

Useful flags:

| flag | effect |
|---|---|
| `--claude` / `--no-claude` | force or skip the Claude Code wiring (default: auto-detect) |
| `--copilot` | maintain `.github/copilot-instructions.md` for GitHub Copilot |
| `--conversations` | opt in to automatic capture from Claude Code session transcripts (default: off) |
| `--no-sync` | initialize without running the first index |

Then start the daemon:

```bash
dot daemon start
dot status
```

The daemon watches the filesystem, serves the API on localhost (port 7337,
or the next free port if that is taken), runs background jobs, and keeps the
index current as you work.

## 3. The command line tour

```bash
dot status                  # what Dot knows: files, chunks, memories, storage
dot ask "where do we validate webhooks?"        # semantic codebase search
dot inject "refactoring the billing module"     # print assembled context
dot inject --fmt claude     # XML format for Claude
dot inject --fmt copilot    # concise comment format
dot inject --profile quick-assist    # ~2k token budget
dot inject --profile deep-dive       # ~8k token budget

dot memory list             # browse captured memories
dot memory list -q "redis"  # semantic search over memories
dot memory add "Chose Redis over Memcached for TTL support" --file cache.py
dot memory add "Decided to shard by tenant" --share     # share with the team
dot memory share <id>       # share an existing memory after the fact
dot memory export -o backup.json     # portable JSON of all memories
dot memory delete <id>      # forget one memory
dot forget "redis"          # forget all memories matching a pattern

dot import                  # pull in new shared memories (after git pull)
dot import backup.json      # import a previously exported file

dot sync                    # force re-index (only changed files touch disk)
dot sync --force            # re-index everything

dot dashboard               # open the web UI
dot daemon start|stop       # background daemon control
dot daemon install-service  # launchd (macOS) / systemd (Linux) unit
dot mcp                     # MCP server on stdio (used by Claude Code)
```

## 4. Feature experiments

A test checklist. Each experiment states what to do and what you should
observe. Run them in order; later ones build on earlier ones.

### Experiment 1: indexing

```bash
cd your-project && dot init && dot daemon start
dot status
```

Expected: files indexed > 0, chunks > files (each file becomes several
function/class chunks), embeddings backend shows
`sentence-transformers/all-MiniLM-L6-v2` if you installed `[ml]`.

### Experiment 2: semantic search

```bash
dot ask "how do we handle authentication"
```

Expected: the files that actually implement auth, even if they never use the
word "authentication". With the hashing fallback you will only get matches
that share literal words; that difference is the whole argument for `[ml]`.

### Experiment 3: live file watching

```bash
echo 'def health_check():\n    """Liveness probe endpoint."""\n    return "ok"' > probe.py
sleep 3
dot ask "liveness probe"
```

Expected: `probe.py` appears in results within seconds of saving, without
running sync. The daemon watches the tree with a debounce of about 1.5
seconds.

### Experiment 4: decision mining from git

```bash
git commit --allow-empty -m "Chose event sourcing over CRUD because audit history is a hard requirement"
sleep 3
dot memory list
```

Expected: a new memory of kind `decision` with source `git:<sha>` and
confidence around 0.95. The post-commit hook pinged the daemon, which parsed
the message. A commit like "fix typo" will not be captured; only messages
that record a rationale are.

### Experiment 5: recency-aware context

Edit any file, save it, then run:

```bash
dot inject "" --file path/to/that-file.py --fmt raw | head -40
```

Expected: the file you just touched ranks near the top. Look at
`score_components` in the output: recency contributes up to 0.20 of the
final score, decaying with a 72 hour half-life.

### Experiment 6: token budget discipline

```bash
dot inject "payments" --budget 500 --fmt raw | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['tokens_used'], '<=', d['token_budget'])"
```

Expected: tokens_used never exceeds the budget. The assembler fills the
budget greedily from the top-ranked chunks and reserves about 20 percent
for decisions.

### Experiment 7: the REST API

```bash
curl 'http://127.0.0.1:7337/status'
curl 'http://127.0.0.1:7337/context?query=auth&fmt=claude'
curl 'http://127.0.0.1:7337/graph' | python3 -m json.tool | head
curl -X POST http://127.0.0.1:7337/memory \
  -H 'content-type: application/json' \
  -d '{"content": "Decided to rate limit by API key", "kind": "decision", "share": true}'
```

Expected: JSON or formatted text from each endpoint, assembly in well under
100 ms (check the `x-dot-assembly-ms` response header on `/context`).

### Experiment 8: memory decay and reinforcement

```bash
dot memory list      # note the weight column
```

Expected: fresh memories weigh about 1.0. Weights halve every 30 days, but
each time a memory is retrieved its access count rises, which pushes the
weight back up. Memories that decay below 0.05 are archived (hidden, not
deleted) by a background job.

### Experiment 9: multiple projects at once

```bash
cd ~/code/project-a && dot daemon start
cd ~/code/project-b && dot daemon start
dot status     # run in each project
```

Expected: both daemons run. The second one finds 7337 occupied, takes 7338,
and records it in its own `.dot/config.json`, so every later command in that
project talks to the right port automatically.

### Experiment 10: the dashboard

```bash
cd <dot-context-engine checkout>/dashboard && npm install && npm run build
# restart the daemon in your project, then:
dot dashboard
```

Expected: a web UI at `/ui` with project stats, a force-directed dependency
graph, a searchable memory timeline, and a context preview page that shows
the exact payload and per-chunk score breakdown for any query.

### Experiment 11: MCP tools in Claude Code

```bash
dot init --claude     # writes .mcp.json registering `dot mcp`
```

Open Claude Code in the project and ask something project-specific.
Expected: Claude can call the native tools `dot_context`, `dot_remember`,
and `dot_status`. Ask it to "record this decision in dot" after making a
choice, and verify with `dot memory list`.

### Experiment 12: capture decisions from Claude Code chats automatically

The manual `/memory/conversation` paste is gone. Opt in once:

```bash
dot init --conversations
```

This sets `capture_conversations` in `.dot/config.json` (off by default). The
daemon then reads local JSONL session transcripts under `~/.claude` (or
`$CLAUDE_CONFIG_DIR`) for this project, extracts decision-bearing assistant
turns, and feeds them through the same capture pipeline as commit messages -
no fork, no network, no transcript pasting. Captures are incremental
(per-file byte offsets) and idempotent (sha256 memory ids), so re-running is
free.

```bash
dot capture     # on-demand scan, prints counts
dot memory list # decisions surface with source conversation:<session-id>
```

Privacy: capture reads **only** local `~/.claude` files for the project you
opted in on, never sends transcript contents anywhere, and is off unless you
run `dot init --conversations`. Point it elsewhere with `CLAUDE_CONFIG_DIR`.

### Experiment 13: the full cross-tool scenario

The product thesis in one test:

1. Work in VS Code on some files. Save them.
2. Switch to Claude Code in the same folder.
3. Give it only a keyword: "rate limiting, write me a script for that".

Expected: Claude pulls context from Dot (recently edited files rank high)
and responds with project-aware output, no re-explaining required.

## 5. Team collaboration

Dot shares memory through git itself. There is no server and no account.

Two layers:

**Automatic:** decisions mined from commit messages have deterministic IDs
(a hash of the commit and content), so every teammate who indexes the same
repository converges on identical memories. Commit-message decisions are
shared by default, by construction.

**Explicit:** everything else (manual captures, decisions recorded from AI
chats) is shared through `dot-memories.jsonl`, a committed, append-only file
at the project root.

```bash
# teammate A
dot memory add "Chose Stripe over Adyen for EU coverage" --share
git add dot-memories.jsonl && git commit -m "share decision" && git push

# teammate B
git pull        # daemon notices the file changed and imports automatically
dot memory list # the decision is there, tagged with author and "shared"
```

If the daemon is not running, `dot import` does the same import on demand.
New clones import everything during `dot init`. Because each line carries a
stable ID and the file is append-only, git merges are conflict-free in
practice and re-imports are always safe.

## 6. AI tool integrations

| tool | mechanism | setup |
|---|---|---|
| Claude Code | MCP server (`dot mcp` via `.mcp.json`), CLAUDE.md, SessionStart hook | `dot init --claude` (or auto-detected) |
| GitHub Copilot | VS Code extension injects context via the Language Model API | build `vscode-extension/`, press F5 or install the vsix |
| Copilot (no extension) | Dot-managed section in `.github/copilot-instructions.md`, refreshed hourly | `dot init --copilot` |
| Cursor / anything | REST API on localhost | `curl localhost:7337/context?query=...` |

To build the VS Code extension:

```bash
cd vscode-extension && npm install && npm run compile
# F5 in VS Code for a dev host, or:
npx @vscode/vsce package && code --install-extension dot-context-0.1.0.vsix
```

## 7. Configuration reference

Everything lives in `.dot/config.json` in the project. Edit it and restart
the daemon.

| key | default | meaning |
|---|---|---|
| `token_budget` | 4000 | default context size in (estimated) tokens |
| `recency_half_life_hours` | 72 | how fast the recency signal fades |
| `memory_half_life_days` | 30 | the forgetting curve half-life |
| `embedding_model` | all-MiniLM-L6-v2 | any sentence-transformers model name |
| `extra_extensions` | `[]` | extra file types to index, e.g. `[".txt"]` |
| `extra_ignored_dirs` | `[]` | additional directories to skip |
| `integrations` | set by init | which tool files Dot maintains ("claude", "copilot") |
| `api_port` | 7337 | preferred port; auto-bumped if busy |
| `profiles` | quick-assist, deep-dive | named context presets (budget, chunk count) |

## 8. Storage

Short answer: no, Dot will not exhaust your disk. Typical cost is tens of
megabytes per project.

What is stored, per project, inside `.dot/`:

- **SQLite database**: chunk text (a copy of your source, roughly the size
  of the code itself), file metadata, memories, dependency edges.
- **Vector index**: with ChromaDB, each chunk costs 384 floats at 4 bytes,
  about 1.5 KB, plus index overhead. In the no-ML fallback, embeddings are
  stored as JSON text in SQLite, which is fatter (roughly 8 KB per chunk),
  another reason to install `[ml]`.

Worked example: a project of 4,000 files producing 12,000 chunks lands
around 30 to 60 MB with ChromaDB. A small project is well under 1 MB.
`dot status` shows the exact figure on the "local storage" row.

One-time global costs: the embedding model (~90 MB) lives in the HuggingFace
cache in your home directory and is shared across all projects; PyTorch
(pulled in by `[ml]`) is the largest install at a few hundred MB, also once.

Cleanup is trivial because everything is in one folder: `rm -rf .dot`
removes a project's entire index, and `dot sync` rebuilds it from scratch
whenever you want.

## 9. Troubleshooting

**`dot ask` returns the wrong project's code.** Your indexed folder probably
contains more than you think (for example, a clone of another repo inside
it). Check the paths in the results, add directories to
`extra_ignored_dirs`, or move the foreign code out and re-run `dot sync`.

**My notes are not in the results.** Check the file extension. Plain `.txt`
is not indexed by default; add `"extra_extensions": [".txt"]` to
`.dot/config.json` and run `dot sync`.

**"no git repository found" at init.** Decision mining and the commit hook
need a git repo. Run `git init`, or ignore the warning if you only want
code search.

**Daemon seems down.** `dot status` says "not running"; restart with
`dot daemon start`. Logs are at `.dot/daemon.log`. If a port message looks
odd, remember the actual port is recorded in `.dot/config.json`.

**Results feel keyword-ish, not semantic.** You are on the hashing fallback.
`dot status` shows the embeddings backend; install `[ml]` and `dot sync --force`.

**Indexing missed a brand-new commit's decision.** The hook fires on commit;
the scheduler also re-mines every 15 minutes. `dot sync` forces it now.

## 10. Uninstall / reset

```bash
dot daemon stop
rm -rf .dot                      # per-project index, config, logs
rm -f dot-memories.jsonl         # only if you also want shared memories gone
rm -rf ~/.dot                    # global daemon bookkeeping (pid files)
pip uninstall dot-context
```

Files written by integrations, if you enabled them: `CLAUDE.md`,
`.claude/settings.json`, `.mcp.json`, `.github/copilot-instructions.md`,
and the git hook at `.git/hooks/post-commit`. All are plain text and safe
to delete.

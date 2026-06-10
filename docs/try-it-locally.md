# Try Dot locally

Dot isn't published to PyPI yet — you install it from this repository. Total
time: about two minutes (plus an optional ~200MB ML download).

## 1. Install

```bash
git clone https://github.com/aryanp-spektra/dot-context-engine.git
cd dot-context-engine

python3 -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -e ".[dev]"

dot version   # → dot 0.1.0
```

**Optional but recommended** — real semantic search instead of the lexical
fallback (downloads torch + the all-MiniLM-L6-v2 model on first index):

```bash
pip install -e ".[ml]"
```

Without `[ml]`, everything still works using a deterministic hashing embedder —
fine for a first look, noticeably weaker on "find me code that *means* X"
queries.

## 2. Point it at a real project

Use any codebase you actually work on — the demo is much more convincing on a
project with months of git history:

```bash
cd ~/code/your-project
dot init            # indexes files, mines git history, installs hooks
dot daemon start    # background daemon on http://127.0.0.1:7337
dot status
```

`dot init` does four things: indexes every source file (AST-chunked, embedded
locally), mines the last 500 commits for decisions ("chose X over Y",
"workaround for…"), installs a git post-commit hook so new commits are captured
live, and wires up Claude Code (CLAUDE.md section + SessionStart hook).

## 3. The five-minute tour

```bash
# natural-language search over your codebase
dot ask "where do we handle authentication?"

# what would be injected into an AI tool right now
dot inject "refactoring the payment flow" --fmt claude
dot inject --profile quick-assist        # tighter budget
dot inject --profile deep-dive           # broader context

# capture a decision by hand
dot memory add "Chose Postgres over MySQL for JSONB support" --file db/schema.sql
dot memory list

# the live-capture loop: commit with rationale, watch it become a memory
git commit -m "Switched to event sourcing because CRUD caused race conditions"
dot memory list      # ← the decision is there, mined from the commit

dot forget "event sourcing"   # remove memories matching a pattern
```

## 4. The REST API (what other tools consume)

```bash
curl 'http://127.0.0.1:7337/status'
curl 'http://127.0.0.1:7337/context?query=rate%20limiting&fmt=claude'
curl 'http://127.0.0.1:7337/context?query=rate%20limiting&fmt=raw' | jq .
curl 'http://127.0.0.1:7337/graph' | jq '.nodes | length'
```

## 5. Web dashboard

The dashboard serves at `http://127.0.0.1:7337/ui` once it's built (one-time,
needs Node 20+):

```bash
cd dot-context-engine/dashboard
npm install && npm run build
# restart the daemon in your project, then:
dot dashboard
```

You get the project overview, a force-directed dependency graph, the searchable
memory timeline, and a context-preview page that shows exactly what Dot would
inject for any query — with per-chunk score breakdowns.

## 6. Team collaboration (shared memory)

Decisions mined from git history are automatically shared — every teammate
mining the same history converges on identical memories. For everything else,
share explicitly:

```bash
dot memory add "Chose Stripe over Adyen for EU coverage" --share
git add dot-memories.jsonl && git commit -m "share decision" && git push
```

`dot-memories.jsonl` is a committed, append-only file. When a teammate pulls,
their daemon notices the change and imports the new memories automatically
(or run `dot memory pull` manually). New clones import everything on
`dot init`. No server, no accounts — git is the sync.

```bash
dot memory share <id>     # share an existing memory after the fact
dot memory pull           # force-import after a git pull
```

## 7. AI tool integrations

**Claude Code** — `dot init` wires it when it detects Claude usage (a
`.claude/` directory or existing CLAUDE.md; force with `--claude`, skip with
`--no-claude`). It registers a real **MCP server** in `.mcp.json`, giving
Claude native `dot_context`, `dot_remember`, and `dot_status` tools — plus
CLAUDE.md instructions and a SessionStart hook as fallbacks.

**GitHub Copilot, no extension** — opt in with `dot init --copilot`; the
daemon then maintains a Dot section in `.github/copilot-instructions.md`
(refreshed hourly) with your top decisions, which Copilot picks up natively.

**VS Code extension** (sidebar, decision capture, Copilot LM tool):

```bash
cd dot-context-engine/vscode-extension
npm install && npm run compile
```

Then open `vscode-extension/` in VS Code and press **F5** to launch an
Extension Development Host, or package it for a real install:

```bash
npx @vscode/vsce package    # → dot-context-0.1.0.vsix
code --install-extension dot-context-0.1.0.vsix
```

## 8. Keep it running / shut it down

```bash
dot daemon stop                  # stop the background daemon
dot daemon install-service      # launchd (macOS) / systemd (Linux) unit
rm -rf .dot                      # nuke everything Dot knows about a project
```

## What to expect (honest notes)

- First index of a large repo takes a few minutes with `[ml]`; re-syncs only
  touch changed files (content-hashed).
- The daemon binds to 127.0.0.1 only. Nothing leaves your machine; the only
  network call ever is the one-time model download from HuggingFace.
- Decision mining is pattern-based — commits phrased like "chose X over Y
  because…" are captured; "fix stuff" is not. Your memories are only as good
  as your commit messages, which is rather the point.
- `tree-sitter` parsing for non-Python languages is an optional extra
  (`pip install -e ".[treesitter]"`); without it a regex heuristic still finds
  functions, classes, and imports in most C-like languages.
- Plain-text content: add extensions in `.dot/config.json`, e.g.
  `"extra_extensions": [".txt"]`, then `dot sync`.
- Running Dot on several projects at once is fine — each daemon grabs the next
  free port automatically and records it in its project's `.dot/config.json`.

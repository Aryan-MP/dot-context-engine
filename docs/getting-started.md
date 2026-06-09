# Getting started

## Install

```bash
pip install dot-context[ml]
```

The `[ml]` extra pulls in ChromaDB and sentence-transformers for real semantic
search (~200MB with torch). Without it, Dot still works using a deterministic
hashing embedder and SQLite vector search — useful for CI, containers, or trying
it out. Add `[treesitter]` for precise AST parsing of non-Python languages.

## Initialize a project

```bash
cd your-project
dot init
```

This:

1. creates `.dot/` (config, SQLite DB, vector index — add it to global gitignore if you like; `dot init` projects already ignore it)
2. runs the first index: every source file is parsed, chunked by function/class, embedded
3. mines the last 500 git commits for architectural decisions ("chose X over Y", "workaround for…", "decided to…")
4. installs a git `post-commit` hook so new commits are captured live
5. adds a Dot section to `CLAUDE.md` and a SessionStart hook for Claude Code

The first run downloads the embedding model (all-MiniLM-L6-v2, ~90MB); subsequent runs are fast.

## Keep it running

```bash
dot daemon start          # background process, watches files, serves the API
dot daemon stop
dot daemon install-service  # launchd (macOS) / systemd (Linux) unit, survives reboots
```

The daemon serves `http://127.0.0.1:7337` (loopback only — nothing is exposed to the
network) and re-indexes changed files within seconds of saving, debounced.

## Use it

```bash
dot status                                   # what Dot knows
dot ask "where do we validate webhooks?"     # semantic codebase search
dot inject "adding rate limiting" --fmt claude   # print context, pipe anywhere
dot memory list                              # browse captured decisions
dot memory add "Chose Redis over Memcached for persistence" --file cache.py
dot forget "redis"                           # remove memories matching a pattern
dot dashboard                                # web UI
```

Context profiles tune size/depth per use:

```bash
dot inject --profile quick-assist    # ~2k tokens, tight
dot inject --profile deep-dive       # ~8k tokens, broad
```

Edit `.dot/config.json` to adjust budgets, half-lives, ignored dirs, and profiles —
see [architecture.md](architecture.md) for what the knobs do.

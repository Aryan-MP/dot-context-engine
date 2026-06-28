# Dot documentation

Dot is an open source, local-first AI context memory daemon. It watches your
codebase, indexes it semantically, captures the decisions behind it, and
serves the right context to every AI tool you use: Claude Code, GitHub
Copilot, Cursor, or anything that can reach `localhost:7337`.

Local. Private. Model-agnostic. Your code never leaves your machine.

## Where to start

<div class="grid cards" markdown>

- **[Getting started](getting-started.md)**

    Install, initialize a project, and verify every feature with twelve
    hands-on experiments. The practical path.

- **[Foundations](foundations.md)**

    Every concept the deep dive assumes, taught from zero: embeddings,
    cosine similarity, ASTs, hashing, decay math, daemons, MCP. Read this
    first if any of those words are new.

- **[Internals](internals.md)**

    The complete technical guide: every module, algorithm, and formula,
    with worked examples. Read foundations first, then this, and you own
    the system.

- **[Integrations](integrations.md)**

    Wiring Dot into Claude Code (MCP), Copilot, Cursor, git hooks, and
    custom tools over the REST API.

</div>

## The product in one minute

```bash
pip install -e ".[ml]"     # from a clone; not on PyPI yet

cd your-project
dot init                    # index code, mine decisions from git history
dot daemon start            # watch files, serve the API on localhost:7337

dot ask "where do we validate webhooks?"
dot memory add "Chose Redis over Memcached for TTL support" --share
```

From that moment, every AI tool in that project starts its session already
knowing your code, your conventions, and the reasons behind them.

## Quick links

- [GitHub repository](https://github.com/Aryan-MP/dot-context-engine)
- [Product website](https://dot-context-engine.vercel.app)
- [Architecture overview](architecture.md) for a shorter tour than internals

# Show HN: Dot — a local-first context memory daemon for AI coding tools

Every AI tool starts from zero. You explain your codebase to Claude Code, then again to Copilot, then again in the next chat. Dot is a local daemon that ends that loop.

It watches your project, indexes code semantically, mines architectural decisions from git history and Claude Code transcripts, and serves ranked context through a local REST API. Nothing leaves your machine: embeddings run locally, storage is SQLite + ChromaDB.

## Quick try

```bash
pip install dot-context[ml]
cd your-project
dot init
dot daemon start
dot ask "how does auth middleware work?"
```

## Why

I wanted a single memory layer that any AI tool could query. Claude Code gets a SessionStart hook and an MCP server. Copilot gets a VS Code extension with a `#dotContext` tool. Custom scripts just `curl localhost:7337/context`.

## Links

- GitHub: https://github.com/Aryan-MP/dot-context-engine
- Docs: https://dot-context-engine.vercel.app/docs
- PyPI: https://pypi.org/project/dot-context/
- VS Code extension: https://marketplace.visualstudio.com/items?itemName=AryanMangod.dot-context-memory

MIT licensed. Would love feedback on the ranking algorithm and the MCP integration.

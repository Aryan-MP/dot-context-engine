# Dot — launch thread

Tweet 1/5 🧵

Tired of explaining your codebase to every AI tool?

Meet Dot: a local-first context memory daemon.

It watches your project, remembers decisions, and feeds the right context to Claude Code, Copilot, Cursor, or any script that can hit localhost.

No code leaves your machine.

Tweet 2/5

How it works:

- Indexes code semantically (function/class level, not token windows)
- Mines decisions from git commits + Claude Code transcripts
- Ranks context by similarity, file proximity, recency, and edit frequency
- Serves it via REST or injects it into Claude/Copilot automatically

Tweet 3/5

One command:

```bash
pip install dot-context[ml]
cd your-project
dot init
dot daemon start
```

Then ask: `dot ask "how does auth work here?"`

Dot remembers what you never wrote down.

Tweet 4/5

Ships with:

- VS Code extension (Copilot `#dotContext` tool + sidebar)
- Claude Code MCP server + SessionStart hook
- Web dashboard at localhost:7337/ui
- MIT licensed, open source

Tweet 5/5

Try it:

- GitHub: https://github.com/Aryan-MP/dot-context-engine
- Website: https://dot-context-engine.vercel.app
- VS Code: https://marketplace.visualstudio.com/items?itemName=AryanMangod.dot-context-memory

Alpha feedback welcome 🙏

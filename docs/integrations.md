# Integrations

Dot is model-agnostic: anything that can hit `http://127.0.0.1:7337` can use it.

## Claude Code

`dot init` wires this when it detects Claude usage in the project (a `.claude/`
directory, CLAUDE.md, or .mcp.json — force with `--claude`):

- an **MCP server** registered in `.mcp.json` (`dot mcp` on stdio), giving
  Claude native tools: `dot_context` (retrieve ranked context),
  `dot_remember` (record a decision, optionally `share: true` for the team),
  and `dot_status`
- a **CLAUDE.md section** telling Claude how to query Dot's REST API
- a **SessionStart hook** in `.claude/settings.json` that injects assembled
  context when a session begins

Manual usage inside any session:

```bash
curl 'http://127.0.0.1:7337/context?query=how%20does%20billing%20work&fmt=claude'
```

The `claude` format is XML-tagged (`<codebase_context>`, `<decisions>`,
`<code_chunks>`) — dense and structured the way Claude parses best.

## VS Code + Copilot

Install the extension from `vscode-extension/` (`npm install && npm run compile`,
then F5 or `vsce package`). It provides:

- **sidebar** ("What Dot knows") — decisions and related code for the active file,
  click to jump
- **Language Model tool** — registers `#dotContext` so Copilot Chat (and any LM
  API consumer) can pull project memory on demand
- **decorations** — hover markers on lines with captured decisions
- **commands** — `Dot: Capture This Decision` (one click from any selection or
  chat), `Show Context`, `Force Re-index`, `Start/Stop Daemon`, `Open Dashboard`
- auto-starts the daemon when a `.dot/` workspace opens

For plain Copilot without the extension, the daemon refreshes a Dot-managed
section of `.github/copilot-instructions.md` hourly with the top-weighted
decisions — Copilot picks that file up natively.

## Git

`dot init` installs a `post-commit` hook that pings `/hooks/git/commit`, so a
decision phrased in a commit message ("chose X over Y because…") becomes a
memory seconds after you commit. A 15-minute scheduled scan catches anything
the hook misses (rebases, pulls).

## Custom tools

```bash
# raw JSON with scores — build your own prompt
curl 'http://127.0.0.1:7337/context?query=auth&fmt=raw' | jq .

# pipe markdown context into any CLI tool
dot inject "reviewing the cache layer" --fmt markdown | llm "explain risks"

# capture a decision from a script or chat-bot hook
curl -X POST http://127.0.0.1:7337/memory \
  -H 'content-type: application/json' \
  -d '{"content": "Decided to shard by tenant id", "kind": "decision", "source": "standup"}'

# extract decisions from a whole conversation transcript
curl -X POST http://127.0.0.1:7337/memory/conversation \
  -H 'content-type: application/json' \
  -d '{"transcript": "...", "source": "claude-chat"}'
```

Context profiles (`?profile=quick-assist` / `deep-dive`, configurable in
`.dot/config.json`) let different tools request different depths without
coordinating token budgets.

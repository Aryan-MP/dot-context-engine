---
layout: ../../layouts/DocsLayout.astro
title: Integrations
description: Wire Dot into Claude Code, GitHub Copilot, Cursor, and anything else over the REST API.
---

Dot is model-agnostic: anything that can reach `http://127.0.0.1:7337` can use
it. Here is how each tool connects.

## Claude Code

`dot init` wires this automatically when it detects Claude usage (force with
`--claude`). It sets up three things:

- **An MCP server** registered in `.mcp.json`, giving Claude native tools:
  `dot_context` (retrieve ranked context), `dot_remember` (record a decision),
  and `dot_status`.
- **A CLAUDE.md section** describing how to query Dot.
- **A SessionStart hook** that injects context when a session begins.

Once wired, just ask Claude something project-specific and it can pull context
itself. To record a decision mid-session, ask it to use `dot_remember`.

## GitHub Copilot

Two paths, depending on whether you use the extension:

- **VS Code extension** - shows a "What Dot knows about this file" sidebar,
  registers Dot as a Language Model tool for Copilot Chat (`#dotContext`), and
  offers one-click decision capture. Grab the `.vsix` from the
  [latest release](https://github.com/Aryan-MP/dot-context-engine/releases/latest).
- **No extension** - run `dot init --copilot`. Dot maintains a managed section
  of `.github/copilot-instructions.md` with your top decisions, refreshed
  automatically, which Copilot reads natively.

## Cursor and everything else

Any editor or script can hit the REST API directly:

```bash
curl 'http://127.0.0.1:7337/context?query=add%20retry%20logic&fmt=markdown'
```

## REST API reference

The daemon serves these on `localhost` only:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/status` | Daemon health and project stats. |
| `GET` | `/context?query=&file=&fmt=&profile=` | Assembled context. `fmt` is `claude`, `copilot`, `markdown`, or `raw`. |
| `POST` | `/ask` | Natural-language query (JSON body). |
| `POST` | `/memory` | Capture a decision. Pass `"share": true` to also write the team file. |
| `GET` | `/memory` | Browse or search memories. |
| `POST` | `/memory/conversation` | Extract decisions from a transcript. |
| `DELETE` | `/memory/{id}` | Forget a memory. |
| `GET` | `/graph` | Dependency graph as JSON. |
| `POST` | `/sync` | Trigger a re-index. |
| `GET` | `/ui` | The web dashboard. |

Example: capture a decision from any script or CI job -

```bash
curl -X POST http://127.0.0.1:7337/memory \
  -H 'content-type: application/json' \
  -d '{"content": "Rate limit by API key", "kind": "decision", "share": true}'
```

## Team sharing

Decisions you mark with `--share` (or `"share": true`) are appended to a
committed `dot-memories.jsonl` file. When a teammate pulls and their daemon sees
the change, it imports the new memories automatically. No server, no accounts -
git is the transport. See [`dot memory share`](/docs/cli) and `dot import`.

Next: the **[FAQ](/docs/faq)**.

---
layout: ../../layouts/DocsLayout.astro
title: Quick start
description: Index your first project, start the daemon, and ask Dot about your code in two minutes.
---

This walks you from an installed Dot to asking questions about a real codebase.
Use a project with some git history; the demo is far more convincing there than
on an empty folder.

## 1. Initialize a project

```bash
cd ~/code/your-project
dot init
```

`dot init` creates a `.dot/` directory (config, database, vector index), adds it
to your `.gitignore`, indexes your code, mines decisions from your git history,
and installs a git post-commit hook so future commits are captured automatically.
If it detects Claude Code in the project, it wires that up too.

## 2. Start the daemon

```bash
dot daemon start
dot status
```

The daemon watches your files, keeps the index current, and serves a local API
on `http://127.0.0.1:7337` (or the next free port, which `dot status` will show).

## 3. Ask about your code

```bash
dot ask "where do we validate webhooks?"
```

Dot returns the functions that actually implement the behaviour, even when they
never use your exact words, along with any relevant captured decisions.

## 4. Capture a decision

```bash
dot memory add "Chose Redis over Memcached for TTL support" --file cache.py
dot memory list
```

Decisions also get mined automatically from commit messages. Try it:

```bash
git commit --allow-empty -m "Switched to event sourcing because audit history is required"
dot memory list
```

The commit's rationale shows up as a captured decision within seconds.

## 5. Feed it to your AI tool

```bash
# print assembled context in Claude's preferred format
dot inject "refactoring the billing module" --fmt claude
```

If you use Claude Code, it can call Dot directly through the MCP tools that
`dot init` registered. See **[Integrations](/docs/integrations)** for every tool.

## The loop, from here on

You do nothing extra. As you work, Dot indexes changes, mines new commit
decisions, and answers any tool that asks. When you switch tools or start a new
chat, the context is already there.

Next: the full **[command reference](/docs/cli)**.

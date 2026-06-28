---
layout: ../../layouts/DocsLayout.astro
title: Overview
description: What Dot is, how it works, and where to go next in the documentation.
---

**Dot** is a local-first AI context memory daemon. It runs quietly beside your
code, builds a deep understanding of your codebase and the decisions behind it,
and serves the right context to any AI tool through a small local API.

You stop re-explaining your project to every new chat, and your AI tools stop
starting from zero.

> Local. Private. Model-agnostic. Open source. Embeddings run on your machine,
> storage is SQLite on your disk, and the only network call Dot ever makes is a
> one-time model download.

## How it fits together

Dot has three jobs, and it does them continuously in the background:

1. **It reads your codebase.** Files are parsed into whole functions and
   classes, embedded locally, and re-indexed within seconds of every save.
2. **It remembers the why.** Decisions are mined from commit messages, code
   comments, and (optionally) your AI conversations, then kept with a gentle
   forgetting curve.
3. **It recalls on demand.** Any tool asks the local API a question; Dot ranks
   everything it knows by relevance, recency and proximity, fits it to a token
   budget, and returns a formatted answer in well under 100ms.

## Where to go next

- **[Installation](/docs/installation)** - get Dot onto your machine.
- **[Quick start](/docs/quickstart)** - index your first project and try it.
- **[Commands](/docs/cli)** - the full CLI reference.
- **[Configuration](/docs/configuration)** - every setting in `.dot/config.json`.
- **[Integrations](/docs/integrations)** - Claude Code, Copilot, Cursor, REST.
- **[FAQ](/docs/faq)** - storage, privacy, Windows, and other common questions.

For the deep technical story (architecture, ranking math, the forgetting curve),
see [`docs/internals.md`](https://github.com/aryanp-spektra/dot-context-engine/blob/main/docs/internals.md)
in the repository.

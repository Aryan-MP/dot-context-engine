---
layout: ../../layouts/DocsLayout.astro
title: FAQ
description: Storage, privacy, Windows, switching models, and other common questions about Dot.
---

## Is my code sent anywhere?

No. Embeddings are generated on your CPU, storage is SQLite and a local vector
index on your disk, and the API binds to `127.0.0.1` only. The single network
call Dot ever makes is a one-time download of the embedding model from Hugging
Face. Run in the light build (no `[ml]`) and even that disappears.

## Will it fill up my disk?

No. A typical project costs tens of megabytes. A small project is under 5 MB; a
large one (thousands of files) lands around 30–60 MB, usually smaller than its
own `.git` directory. `dot status` shows the exact size. To reclaim it all,
delete the `.dot/` folder; `dot sync` rebuilds it.

## Does it work on Windows?

Yes - macOS, Linux, and Windows. The daemon lifecycle is cross-platform. On
macOS and Linux you can install it as a background service with
`dot daemon install-service`; on Windows, launch `dot daemon start` (for example
via Task Scheduler) to keep it running.

## Do I need a GPU or an API key?

Neither. The default model (`all-MiniLM-L6-v2`) runs comfortably on a CPU, and
Dot never calls a hosted LLM - it does retrieval, your tools do generation.

## My notes/docs aren't being indexed.

Check the file extension. Common code and docs extensions are indexed by
default; to add more (like `.txt`), set `extra_extensions` in
`.dot/config.json` and run `dot sync`. See [Configuration](/docs/configuration).

## Can I change the embedding model?

Yes, via `embedding_model` in the config - but vectors from different models are
not comparable, so run `dot sync --force` afterwards to rebuild the index.

## How does it decide what's a "decision"?

It looks for rationale in commit messages, comments, and (optionally) AI chats:
phrases like "chose X over Y because…", "decided to…", "workaround for…". A
commit like "fix typo" is ignored. Your memory is only as good as your commit
messages, which is rather the point.

## What does it cost?

Nothing. Dot is open source under the MIT license, free forever, and runs
entirely on your machine.

## How do I remove it completely?

```bash
dot daemon stop
rm -rf .dot                 # the project's index and config
rm -f dot-memories.jsonl    # only if you also want shared memories gone
pip uninstall dot-context
```

Integration files (`CLAUDE.md`, `.mcp.json`, `.github/copilot-instructions.md`)
and the git post-commit hook are plain text and safe to delete by hand.

## Where's the deep technical documentation?

The repository's [`docs/internals.md`](https://github.com/aryanp-spektra/dot-context-engine/blob/main/docs/internals.md)
covers the architecture, ranking math, and storage design in depth, and
[`docs/foundations.md`](https://github.com/aryanp-spektra/dot-context-engine/blob/main/docs/foundations.md)
teaches the underlying concepts from zero.

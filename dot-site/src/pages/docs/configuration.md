---
layout: ../../layouts/DocsLayout.astro
title: Configuration
description: Every setting in .dot/config.json, what it does, and its default.
---

Each project's settings live in `.dot/config.json`, created by `dot init`. Edit
the file and restart the daemon (`dot daemon stop && dot daemon start`) to apply
changes.

## Settings

| Key | Default | What it does |
|---|---|---|
| `embedding_model` | `all-MiniLM-L6-v2` | The sentence-transformers model used for semantic search. Changing it requires a full re-index (`dot sync --force`). |
| `token_budget` | `4000` | Default size of an assembled context, in estimated tokens. |
| `recency_half_life_hours` | `72` | How fast the recency signal fades. Lower = recent edits dominate more. |
| `memory_half_life_days` | `30` | The forgetting-curve half-life for captured memories. |
| `api_host` | `127.0.0.1` | Host the local API binds to. Keep it on loopback. |
| `api_port` | `7337` | Preferred port; auto-bumped to the next free one if busy. |
| `extra_extensions` | `[]` | Extra file extensions to index, e.g. `[".txt", ".rst"]`. |
| `extra_ignored_dirs` | `[]` | Extra directories to skip, on top of the built-in ignore list. |
| `integrations` | `[]` | Which tool integrations Dot maintains (`"claude"`, `"copilot"`). Set by `dot init`. |
| `capture_conversations` | `false` | Opt in to mining decisions from local Claude Code transcripts. |
| `profiles` | see below | Named context presets you can select with `dot inject --profile`. |

## Profiles

Profiles let different tools request different depths of context without
juggling token budgets. Two ship by default:

```json
{
  "profiles": {
    "quick-assist": { "token_budget": 2000 },
    "deep-dive":    { "token_budget": 8000 }
  }
}
```

Use one with:

```bash
dot inject "payments" --profile deep-dive
```

## Example config

```json
{
  "embedding_model": "all-MiniLM-L6-v2",
  "token_budget": 4000,
  "recency_half_life_hours": 72,
  "memory_half_life_days": 30,
  "api_host": "127.0.0.1",
  "api_port": 7337,
  "extra_extensions": [".txt"],
  "extra_ignored_dirs": ["fixtures", "vendor"],
  "integrations": ["claude"],
  "capture_conversations": false
}
```

## A note on changing the embedding model

Embeddings from two different models are not comparable, so if you change
`embedding_model`, run `dot sync --force` afterwards to rebuild the index.
Mixing old and new vectors will produce poor search results.

Next: **[Integrations](/docs/integrations)**.

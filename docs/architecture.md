# Architecture

Dot is a single Python daemon per project, plus thin clients (CLI, VS Code
extension, web dashboard) that all talk to the same local REST API.

```
┌──────────────────────────── dot daemon (localhost:7337) ───────────────────────────┐
│                                                                                     │
│  watcher (watchdog, debounced)        APScheduler jobs                              │
│      │                                  · git decision mining (15 min)              │
│      ▼                                  · memory decay pruning (6 h)                │
│  parser (ast / tree-sitter / regex)     · copilot-instructions refresh (1 h)        │
│      │                                                                              │
│      ▼                                                                              │
│  chunker (function/class boundaries)                                                │
│      │                                                                              │
│      ▼                                                                              │
│  embedder (sentence-transformers, local, batched, cached)                           │
│      │                                                                              │
│      ▼                                                                              │
│  store ── SQLite (truth: chunks, files, edges, memories)                            │
│        └─ ChromaDB (vector index; SQLite brute-force fallback)                      │
│      │                                                                              │
│      ▼                                                                              │
│  context assembler ──▶ ranker ──▶ budget filler ──▶ formatter ──▶ /context          │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Indexing pipeline (dot/indexer/)

- **watcher.py** — watchdog observer with a 1.5s debounce so editor write bursts
  collapse into one event. Ignores `node_modules`, `.venv`, etc.
- **parser.py** — three strategies in preference order: Python's builtin `ast`
  (exact, always available), tree-sitter via `tree-sitter-language-pack` (optional
  extra, 30+ languages), and a regex heuristic fallback. Extracts functions,
  classes + hierarchy, imports, and annotated comments (`TODO`, `FIXME`,
  `NOTE`, plus "why" phrases like *decided to*, *chose X over Y*, *workaround for*).
- **chunker.py** — chunks align to symbol boundaries. Oversized classes become a
  skeleton chunk (signature + docstring) with methods chunked individually;
  oversized functions split on blank lines; tiny adjacent functions merge.
  Each chunk embeds with a `path :: symbol (kind)` header so identical code in
  different modules still embeds distinctly.
- **embedder.py** — all-MiniLM-L6-v2 locally (384-dim, normalized), batched with
  an in-process content-hash cache. The no-ML fallback is feature hashing over
  identifiers into the same 384 dims, so the two backends are interchangeable
  on disk.

Files are content-hashed; unchanged files are skipped on re-sync.

## Memory (dot/memory/)

- **store.py** — SQLAlchemy/SQLite is the source of truth; ChromaDB holds vectors
  (per-project, under `.dot/chroma`). Every chunk upsert replaces the file's old
  chunks and dependency edges atomically.
- **decisions.py** — pattern-based decision extraction from commit messages,
  comments, and conversation transcripts. Captures are idempotent (memory id =
  hash of source + content), so re-mining git never duplicates.
- **decay.py** — the forgetting curve:
  `weight = confidence · 2^(−age/half_life) · (1 + 0.25·ln(1+accesses))`.
  Querying a memory bumps its access count (reinforcement). A periodic job
  archives memories below the 0.05 threshold — archive, not delete, so
  `dot memory export` keeps full history.

## Context assembly (dot/context/)

`/context` runs the canonical algorithm: vector-search the query, add
same-module chunks, the current file's own chunks, and recently modified
chunks, pull matching memories, then rank everything:

| signal | weight | source |
|---|---|---|
| semantic similarity | 0.45 | cosine against query embedding |
| file proximity | 0.20 | shared path prefix; same dir ≈ 0.85, same file = 1.0 |
| recency | 0.20 | exponential decay, 72h half-life (configurable) |
| edit frequency | 0.10 | log-scaled per-file edit count |
| tag boost | 0.05 | DECISION/FIXME/HACK comments |

Deduplication keeps the best-scoring instance and drops chunks whose line range
a higher-ranked chunk already covers. The budget filler is greedy: 20% of the
budget is reserved for decisions, the rest filled top-down, skipping chunks that
don't fit (a smaller, lower-ranked chunk may still make it).

**formatter.py** renders the result as Claude XML, concise Copilot comments,
markdown, or raw JSON with per-chunk score breakdowns.

## API and daemon

`dot/api.py` is a FastAPI app; `dot/daemon.py` wires watcher + scheduler +
uvicorn into one process, manages PID files under `~/.dot/`, and can emit
launchd/systemd user units. The built dashboard (if `dashboard/dist` exists) is
served at `/ui`. Everything binds to 127.0.0.1 only.

## Privacy model

- No network calls at runtime (the embedding model downloads once from
  HuggingFace at first index; after that everything is offline).
- All state lives in `.dot/` inside your project and `~/.dot/` for daemon
  bookkeeping.
- `dot memory export` produces portable JSON; `rm -rf .dot` removes everything.

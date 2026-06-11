# Dot internals: the complete technical guide

> New to embeddings, vector search, ASTs, or daemons? Read
> [foundations.md](foundations.md) first. It teaches every concept this
> document assumes, from zero, with worked examples, and ends with a map of
> which chapter unlocks which section here.

This document explains every part of Dot in depth: the problem, the
architecture, the algorithms, the math, the storage layout, the protocols,
and the trade-offs behind each decision. It is written so that one careful
read gives you full ownership of the system. Code references point at real
files; every formula is shown with a worked example.

## Contents

1. [The problem and the design principles](#1-the-problem)
2. [System overview: the life of a file save](#2-system-overview)
3. [Concepts primer: embeddings, vector search, chunking](#3-concepts-primer)
4. [The indexing pipeline](#4-the-indexing-pipeline)
5. [Storage: SQLite + ChromaDB](#5-storage)
6. [Memory: decisions, decay, reinforcement](#6-memory)
7. [Context assembly: the core algorithm](#7-context-assembly)
8. [Ranking math, worked example](#8-ranking-math)
9. [Formatters: one payload, many tools](#9-formatters)
10. [The daemon: threads, jobs, ports, lifecycle](#10-the-daemon)
11. [The REST API](#11-the-rest-api)
12. [The MCP server](#12-the-mcp-server)
13. [Team shared memory](#13-team-shared-memory)
14. [Integrations: Claude Code, Copilot, git](#14-integrations)
15. [Storage footprint analysis](#15-storage-footprint)
16. [Performance characteristics](#16-performance)
17. [Privacy and security model](#17-privacy-and-security)
18. [Graceful degradation map](#18-graceful-degradation)
19. [Known limits and extension points](#19-known-limits-and-extension-points)

---

## 1. The problem

Every AI coding tool starts each session with zero knowledge of your
project. You explain your stack to Claude, then again to Copilot, then
again tomorrow. Worse, the *why* of a codebase (decisions, rejected
approaches, hard-won lessons) lives nowhere at all: it evaporates when a
chat closes or an engineer leaves.

Dot's answer is a per-project daemon that builds and maintains two kinds of
knowledge:

- **What**: a semantically indexed map of the code itself.
- **Why**: a memory of decisions, mined automatically and captured manually.

It then serves the most relevant slice of that knowledge to any AI tool, on
demand, in the format that tool prefers.

Three principles shape every design choice:

1. **Local first.** All computation and storage happen on the developer's
   machine. The only network call ever is a one-time embedding model
   download. This is non-negotiable because the input is the most sensitive
   asset a company has: its source code.
2. **Model agnostic.** Dot is retrieval, not generation. It never calls an
   LLM. Whatever model the user's tools run, Dot feeds it.
3. **Degrade gracefully.** Heavy dependencies (PyTorch, ChromaDB,
   tree-sitter) are optional extras. Without them, every feature still
   works through lighter fallbacks. The system should never refuse to run.

## 2. System overview

The fastest way to understand Dot is to trace one file save end to end.

You save `billing/payments.py` in your editor.

1. **Watcher** (`dot/indexer/watcher.py`). A `watchdog` observer sees the
   filesystem event. Editors often write a file several times in quick
   succession (temp file, rename, format-on-save), so events go into a
   pending map keyed by path, and only fire after 1.5 seconds of quiet.
   One save burst becomes one event.
2. **Relevance filter.** The path must have an indexable extension and not
   live under an ignored directory (`node_modules`, `.venv`, `.git`, ...).
   The shared memories file `dot-memories.jsonl` passes the filter
   specially: it is routed to the memory importer, not the code indexer.
3. **Content hash check** (`dot/daemon.py`, `index_file`). The file's
   SHA-256 is compared with the stored hash. Unchanged content means stop
   here; this is what makes `dot sync` cheap.
4. **Parser** (`dot/indexer/parser.py`). The source is parsed into symbols:
   functions, classes, methods, imports, and annotated comments. Three
   strategies, best available wins: Python's builtin `ast` for `.py`,
   tree-sitter for other languages when installed, a regex heuristic
   otherwise.
5. **Chunker** (`dot/indexer/chunker.py`). Symbols become chunks aligned to
   semantic boundaries. A function is one chunk. A huge class becomes a
   skeleton chunk plus per-method chunks. Tiny adjacent functions merge.
6. **Embedder** (`dot/indexer/embedder.py`). Each chunk's text is turned
   into a 384-dimensional unit vector, locally, in batches, with a
   content-hash cache so identical text is never embedded twice.
7. **Store** (`dot/memory/store.py`). In one transaction: the file's old
   chunks and dependency edges are deleted, new ones inserted, the file
   record's hash and edit count updated. Vectors go to ChromaDB (or stay in
   SQLite in fallback mode).

Total cost for a typical file: tens of milliseconds plus embedding time.
From that moment, any query through any surface (CLI, REST, MCP, extension)
can retrieve the new content.

On the query side the flow is: query text is embedded, candidates are
gathered through four channels (similarity, proximity, recency, decisions),
scored, deduplicated, fitted into a token budget, and formatted. Sections 7
to 9 cover this in detail.

## 3. Concepts primer

If you already know embeddings and vector search, skip ahead.

### Embeddings

An embedding model maps text to a point in a high-dimensional space such
that *similar meaning lands close together*. Dot uses all-MiniLM-L6-v2, a
6-layer transformer distilled for sentence similarity: small (90 MB), fast
on CPU, 384 dimensions.

The crucial property: `def authorize(amount, card_token)` and the question
"how do we charge a credit card" end up near each other even though they
share no words. Keyword search cannot do this; embedding search can.

Vectors are L2-normalized (unit length), so similarity is measured with
**cosine similarity**: the dot product of two unit vectors, ranging from -1
(opposite) through 0 (unrelated) to 1 (identical). In code:
`cosine_similarity` in `dot/indexer/embedder.py`.

### The hashing fallback

Without sentence-transformers installed, Dot builds vectors by *feature
hashing*: every identifier-like token in the text is hashed to one of 384
buckets with a +1 or -1 contribution, then the vector is normalized. Two
texts that share many tokens get similar vectors. This preserves lexical
similarity (shared words) but not semantic similarity (shared meaning).
It needs zero dependencies and is deterministic, which also makes tests
stable. The dimensionality matches MiniLM's on purpose so the two backends
are interchangeable on disk.

### Why chunking matters

You cannot embed a whole file as one vector: the meaning gets averaged into
mush, and you cannot inject a 2,000-line file into a prompt anyway. You
also should not chunk by a fixed token count: window number 7 might start
in the middle of one function and end in the middle of another, which makes
both retrieval and injection worse.

Dot chunks on *symbol boundaries*. A chunk is a complete function, class,
or module fragment, with its name, location, and docstring attached. The
embedding input is prefixed with `path :: symbol (kind)` so that two
identical helper functions in different modules still embed distinctly.

### How Dot differs from plain RAG

Standard RAG is: chunk by tokens, embed, retrieve top-k by similarity,
stuff into prompt. Dot differs in four ways: structure-aware chunking,
multi-signal ranking (similarity is only 45 percent of the score), a
separate memory channel for the why (decisions with their own lifecycle),
and continuous incremental indexing instead of one-shot ingestion.

## 4. The indexing pipeline

### 4.1 Watcher (`dot/indexer/watcher.py`)

`ProjectWatcher` wraps a watchdog observer plus a debounce loop:

- Events land in `_pending: dict[Path, _PendingChange]` under a lock; a
  newer event for the same path replaces the older one.
- A flusher thread wakes every 0.5 s and fires callbacks for entries older
  than `debounce_seconds` (1.5 s).
- Moves are treated as delete + create. Directory events are ignored.

`walk_project` is the batch counterpart used by full syncs: an `rglob` over
the tree applying the same extension and ignore rules. Both consult
`config.indexable_extensions`, which is the built-in set plus the per
project `extra_extensions`.

### 4.2 Parser (`dot/indexer/parser.py`)

Output type: `ParsedFile` with `symbols` (functions, classes, methods,
each carrying name, line range, signature, docstring, class bases),
`imports` (module names this file depends on), and `comments` (annotated
comment blocks).

**Strategy 1, Python `ast`.** Exact and always available. The visitor walks
the tree collecting `FunctionDef`, `AsyncFunctionDef`, `ClassDef`,
`Import`, `ImportFrom`. Methods are namespaced as `Class.method`. Docstrings
come from `ast.get_docstring`.

**Strategy 2, tree-sitter.** For the other 30+ languages, when the optional
`tree-sitter-language-pack` is installed. The walker matches node types
(`function_declaration`, `class_specifier`, `impl_item`, ...) across
languages and extracts names through the `name`/`declarator` fields.

**Strategy 3, regex heuristics.** Three patterns find function definitions,
class-like declarations, and imports in most C-family languages. Block ends
are estimated by brace counting. Imprecise, but it means a TypeScript file
is still searchable on a machine with no tree-sitter.

**Comment mining.** Any line tagged `TODO`, `FIXME`, `NOTE`, `HACK`, `XXX`,
`WHY`, `DECISION`, or phrased like a rationale ("decided to", "chose X over
Y", "workaround for", "instead of", "trade-off") is captured with one line
of context above and two below. These become small chunks of kind
`comment` and get a ranking boost later, because they carry the why.

### 4.3 Chunker (`dot/indexer/chunker.py`)

Token math throughout Dot uses a cheap estimate: `len(text) // 4`. It is
within ~15 percent of real tokenizers on code, free, and dependency-less,
which is the right trade for budget enforcement.

Rules, applied to the parsed symbols:

1. **One symbol, one chunk** when the symbol fits within `MAX_CHUNK_TOKENS`
   (500 estimated tokens).
2. **Oversized class**: emit a skeleton chunk (signature plus docstring)
   and let each method become its own chunk. Retrieval can then return
   "what this class is" separately from "this one method".
3. **Oversized function**: split at blank-line boundaries into parts named
   `name (part 1)`, `name (part 2)`.
4. **Module remainder**: lines not covered by any symbol (imports,
   constants, top-level statements) form a `<module>` chunk if they amount
   to at least `MIN_CHUNK_TOKENS` (30).
5. **Tiny-chunk merging**: adjacent small functions of the same kind within
   3 lines of each other merge into one chunk, so embeddings are not wasted
   on three-line getters.

Each chunk's identity is `sha256(file_path :: symbol :: content)[:16]`.
Content-addressed IDs mean an unchanged function keeps its ID across
re-indexes, and any edit produces a new one.

### 4.4 Embedder (`dot/indexer/embedder.py`)

- Lazy model load on first use, guarded by a double-checked lock so
  concurrent indexing threads do not load the model twice.
- Batching at 64 texts per `model.encode` call.
- In-process cache keyed by SHA-256 of the text. A re-index of a file where
  only one function changed re-embeds only that function.
- `normalize_embeddings=True` so cosine similarity is a plain dot product.
- Any model failure (not installed, download blocked, corrupted cache)
  flips permanently to the hashing fallback for the process lifetime, with
  a log line, never an exception to the caller.

## 5. Storage

Dot uses two stores with a clear division of labor. **SQLite is the source
of truth** for all content and metadata. **ChromaDB holds only vectors**
for fast approximate nearest-neighbor search. If ChromaDB is absent, the
vectors live in SQLite as JSON and search is brute force.

### 5.1 SQLite schema (`dot/memory/store.py`)

Four tables, managed by SQLAlchemy:

```
chunks(chunk_id PK, file_path, language, kind, symbol,
       start_line, end_line, content, docstring, tags,
       embedding_json, created_at, updated_at)

files(file_path PK, content_hash, language, edit_count,
      last_indexed, last_modified)

dependencies(id PK, source_file, target_module)

memories(memory_id PK, kind, content, source, file_path, project,
         tags, confidence, access_count, archived,
         embedding_json, created_at)
```

Notes on the design:

- `chunks.content` stores the chunk text itself. This duplicates the source
  on disk, deliberately: retrieval must return text without re-reading
  files that may have changed or vanished, and it keeps the read path to
  one query.
- `files.edit_count` increments on every re-index of a file; it feeds the
  edit-frequency ranking signal.
- `dependencies` rows come from import statements; the graph endpoint
  resolves module names like `dot.indexer.parser` to project file paths by
  suffix matching, marking edges internal or external.
- `memories.archived` is a soft-delete flag used by the forgetting curve;
  archived memories disappear from queries but survive for export.
- `embedding_json` is empty when ChromaDB is active.

Upserting a file's chunks is transactional: delete old chunks and edges for
those paths, insert new ones, bump the file record, commit, then update
ChromaDB. A crash mid-way leaves SQLite consistent; the vector index is
reconciled on the next sync.

### 5.2 Vector search

With ChromaDB: two persistent collections, `chunks` and `memories`, cosine
space, stored under `.dot/chroma`. Query cost is roughly logarithmic via
HNSW graphs.

Fallback: load every `(id, embedding_json)` row, compute cosine similarity
in Python, sort, take the top k. Linear, but fine to tens of thousands of
chunks (a 10k-chunk scan is a few hundred milliseconds), and it keeps the
zero-dependency promise.

ChromaDB returns distances; Dot converts to similarity as `1 - distance`
so both backends speak the same scale.

## 6. Memory

### 6.1 What a memory is

A memory is a small piece of "why" knowledge with a lifecycle:

```
kind        decision | rejected | action_item | note | conversation
content     the text itself
source      git:<sha> | manual | conversation | claude-code | api | shared
confidence  0..1, set by the capture pattern that matched
tags        free-form, e.g. issue:42, author:Maya, shared
access_count  bumped every time the memory is retrieved
```

### 6.2 Decision mining (`dot/memory/decisions.py`)

`parse_decision` runs a table of regex patterns over free text. Each
pattern carries a kind and a confidence:

| pattern | kind | confidence |
|---|---|---|
| "chose X over Y" | decision | 0.95 |
| "decided to" | decision | 0.90 |
| BREAKING / deprecat... | decision | 0.90 |
| "refactored ... because" | decision | 0.85 |
| "workaround for" | decision | 0.80 |
| "rejected", "ruled out", "won't use" | rejected | 0.80 |
| "trade-off" | decision | 0.70 |
| "switched to" | decision | 0.70 |
| "fixed by", "instead of" | decision | 0.60 |
| "TODO:" | action_item | 0.50 |
| "NOTE:" | note | 0.50 |

The highest-confidence match wins. Issue references (`#123`, `JIRA-456`)
become tags. The captured content is the first six non-empty lines, enough
to carry the rationale without swallowing a whole commit body.

Sources mined: the last 500 commit messages (`extract_decisions_from_git`,
which also attaches the most-touched file for proximity ranking and an
author tag), annotated comments from the parser, and conversation
transcripts posted to `/memory/conversation` (split into paragraphs, each
parsed independently).

**Idempotency is the key trick.** A mined memory's ID is
`sha256(source :: content)[:36]`. Re-mining the same history, on the same
machine or any teammate's, produces the same IDs, and `session.merge` makes
the insert an upsert. This is why git mining can run every 15 minutes
forever without duplicating anything, and why commit decisions are
automatically identical across a whole team.

### 6.3 The forgetting curve (`dot/memory/decay.py`)

Memories age. The effective weight of a memory at any moment is:

```
weight = confidence * 2^(-age_days / half_life) * (1 + 0.25 * ln(1 + accesses))
```

Worked example with the default 30-day half-life:

| memory | confidence | age | accesses | weight |
|---|---|---|---|---|
| fresh manual capture | 1.0 | 0 d | 0 | 1.00 |
| month-old decision | 0.95 | 30 d | 0 | 0.48 |
| month-old, retrieved 10 times | 0.95 | 30 d | 10 | 0.76 |
| year-old, never used | 0.95 | 365 d | 0 | 0.0002 |
| year-old, used constantly | 0.95 | 365 d | 50 | 0.0004 |

Two behaviors fall out of the formula. First, retrieval is reinforcement:
every time a memory is returned by a query its access count rises (done
inside `query_memories`), so the knowledge people actually use stays warm,
like spaced repetition. Second, decay always wins eventually, which is
correct: a decision about a system that was rewritten a year ago should
fade no matter how loved it once was.

A background job archives memories whose weight drops below 0.05. Archive,
not delete: `dot memory export` still includes them, so history is never
silently destroyed.

At query time, memories are ranked by `similarity * (0.5 + 0.5 * weight)`,
which lets a very relevant old memory still beat a vaguely relevant new one.

## 7. Context assembly

`dot/context/assembler.py` implements the product's core loop. Given a
query, an optional current file, and a token budget:

**Gather** candidates through four channels:

1. *Similarity*: top 20 chunks by vector search on the query. If the query
   is empty (a tool just asking "context for this file"), the file path
   itself is embedded as the anchor.
2. *Proximity*: 10 most recently updated chunks from the same directory,
   plus all chunks of the current file itself.
3. *Recency*: 10 chunks modified in the last 24 hours, regardless of
   directory or similarity.
4. *Decisions*: top 5 memories by the memory ranking above.

The channels deliberately overlap. A chunk that is similar AND nearby AND
recent enters the pool three times; deduplication keeps the best similarity
seen for it, and its final score reflects all three signals.

**Rank and deduplicate** (next section).

**Fill the budget** greedily: about 20 percent of the budget is reserved
for decisions (they are short and dense with why, and would otherwise be
crowded out by code), then chunks are taken top-down. A chunk that does not
fit is skipped rather than ending the loop, so a small lower-ranked chunk
can still use remaining space. Estimated token counts include a small
per-item overhead for headers and code fences.

Profiles (`quick-assist` at ~2,000 tokens, `deep-dive` at ~8,000, both
configurable) let different tools ask for different depths without
coordinating budgets.

The result carries its own telemetry: `tokens_used`, `assembly_ms`, and per
chunk score components, which the dashboard's context preview displays.

## 8. Ranking math

`dot/context/ranker.py`. The final score of a chunk is a weighted blend:

```
score = 0.45 * similarity        (cosine vs the query)
      + 0.20 * proximity         (path distance to the current file)
      + 0.20 * recency           (2^(-age_hours / 72))
      + 0.10 * edit_frequency    (ln(1 + edits) / ln(50), capped at 1)
      + 0.05 * tag_boost         (DECISION 1.0, FIXME 0.8, HACK 0.7, TODO 0.5)
```

Proximity: 1.0 for the same file, about 0.85 for the same directory,
decaying with the share of common path prefix otherwise, 0 when there is no
current file.

Worked example. Query: "rate limiting", current file
`payments/limiter.ts`, hour ago you edited `auth/limiter.ts`.

| chunk | sim | prox | rec | freq | tag | score |
|---|---|---|---|---|---|---|
| `auth/limiter.ts` rateLimit() | 0.78 | 0.35 | 0.99 | 0.45 | 0 | **0.664** |
| `payments/limiter.ts` (current file) | 0.55 | 1.00 | 0.99 | 0.30 | 0 | **0.675** |
| `docs/adr/rate-limits.md` | 0.81 | 0.20 | 0.01 | 0.05 | 0 | 0.416 |
| `vendor/lib/throttle.js` | 0.70 | 0.10 | 0.01 | 0.02 | 0 | 0.339 |

The fresh, related, frequently-edited implementation and the current file
beat a more textually similar but stale document and a vendored library.
That ordering is the entire reason similarity is only 45 percent of the
score: in a working session, *what you are doing right now* is context, not
just what matches the words.

Deduplication also removes containment overlaps: if a whole class chunk is
already ranked higher, its individual methods (whose line ranges fall
inside it, same file) are dropped so the budget is not spent twice on the
same lines.

## 9. Formatters

`dot/context/formatter.py` renders one `AssembledContext` four ways:

- **claude**: XML-tagged (`<codebase_context>`, `<decisions>`,
  `<code_chunks>` with file/symbol/lines/relevance attributes). Dense,
  structured, matches how Claude parses best.
- **copilot**: comment-style lines (`// [decision] ...`,
  `// --- file:line symbol ---`). Copilot context windows are tight, so
  this format is token-frugal and inline-friendly.
- **markdown**: readable headings and fenced code, for chat tools and
  humans.
- **raw**: full JSON including per-chunk `score_components`, for custom
  integrations and debugging.

One assembly, many consumers: the ranking logic never changes per tool,
only the rendering.

## 10. The daemon

`dot/daemon.py`. One process per project. Inside it:

- **uvicorn** serving the FastAPI app (main thread).
- **watcher** observer + debounce flusher (two threads).
- **initial sync** thread on startup, so the API is responsive immediately
  while the index warms.
- **APScheduler** background jobs: re-mine git every 15 minutes (catches
  pulls and rebases the commit hook missed), prune decayed memories every 6
  hours, refresh Copilot instructions hourly (only when that integration is
  enabled).
- An index lock serializes store writes between the sync thread and watcher
  callbacks.

**Port resolution.** Daemons prefer port 7337. `resolve_port` binds
experimentally; if the port is taken (another project's daemon), it walks
up to the next free port and *persists the result to the project's
config*, so every CLI command, hook, and integration in that project
agrees on the address afterward. This is what lets many projects run Dot
simultaneously.

**PID files** live in `~/.dot/daemon-<hash-of-project-root>.pid`
containing pid, port, and root. `dot daemon start` backgrounds
`dot daemon run` with output to `.dot/daemon.log`; `stop` reads the PID and
sends SIGTERM; a stale PID file (process gone) is cleaned automatically.

**Service install** writes a launchd plist (macOS) or a systemd user unit
(Linux) and prints the enable command rather than running it, staying
non-destructive. Windows users run the daemon via Task Scheduler.

## 11. The REST API

`dot/api.py`, bound to 127.0.0.1 only.

| endpoint | purpose |
|---|---|
| `GET /status` | health, stats, storage size, uptime |
| `GET /context?query=&file=&fmt=&token_budget=&profile=` | the product: assembled context |
| `POST /ask` | same engine, question-shaped body |
| `POST /memory` | capture a memory; `"share": true` also exports to the team file |
| `POST /memory/conversation` | extract decisions from a chat transcript |
| `GET /memory?kind=&query=&limit=` | browse or semantically search memories |
| `GET /memory/export` | portable JSON of all memories |
| `DELETE /memory/{id}` | forget |
| `GET /graph` | dependency graph nodes + edges |
| `POST /sync` | trigger re-index in a background thread (returns 202) |
| `POST /hooks/git/commit` | the git post-commit hook target; mines the latest commits |
| `GET /ui` | the built dashboard, when `dashboard/dist` exists |

Design notes: formatted context responses carry the assembly time in an
`x-dot-assembly-ms` header. CORS allows only the Vite dev server origin so
dashboard development works against a live daemon. Pydantic models validate
all inputs, e.g. memory content has a minimum length and confidence is
clamped to 0..1.

## 12. The MCP server

`dot/integrations/mcp.py`. MCP (Model Context Protocol) is the standard
that lets Claude Code and other clients call tools in external processes.
Dot implements it directly over stdio with no SDK dependency: newline
delimited JSON-RPC 2.0, stdout for protocol, stderr for logs.

Methods handled: `initialize` (capability handshake), `notifications/*`
(acknowledged silently, notifications get no response by spec), `ping`,
`tools/list`, `tools/call`. Errors use JSON-RPC codes (-32601 unknown
method, -32602 unknown tool, -32700 parse error); tool-level failures
return `isError: true` with a message instead of crashing the session.

The three tools:

- `dot_context(query, file?)`: assemble and return markdown context.
- `dot_remember(content, kind?, share?)`: record a decision; with
  `share: true` it also appends to the team file.
- `dot_status()`: index stats as JSON.

A real exchange looks like:

```
→ {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
← {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",
   "capabilities":{"tools":{}},"serverInfo":{"name":"dot","version":"0.1.0"}}}
→ {"jsonrpc":"2.0","method":"notifications/initialized"}
→ {"jsonrpc":"2.0","id":2,"method":"tools/list"}
← {"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}
→ {"jsonrpc":"2.0","id":3,"method":"tools/call",
   "params":{"name":"dot_context","arguments":{"query":"payment provider"}}}
← {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"..."}],
   "isError":false}}
```

The server builds its store lazily on the first tool call, so a session
that never uses Dot costs nothing. Registration is per-project via
`.mcp.json` (`{"mcpServers": {"dot": {"command": "dot", "args": ["mcp"]}}}`),
written by `dot init` when the Claude integration is on. Note the MCP path
reads the store directly; it does not require the HTTP daemon to be up.

## 13. Team shared memory

`dot/memory/shared.py`. The collaboration design follows one observation:
the team already has a synchronized, versioned, access-controlled data
channel: the git repository. So shared memory is a file in the repo, not a
service.

`dot-memories.jsonl` at the project root. One JSON object per line:

```json
{"id": "1758...", "kind": "decision",
 "content": "Chose Stripe over Adyen for EU coverage",
 "source": "manual", "file_path": "", "tags": [],
 "confidence": 1.0, "created_at": "2026-06-10T18:41:30+00:00",
 "author": "Maya"}
```

Why this design holds up:

- **Append-only + stable IDs = conflict-free merging.** Two teammates
  sharing different memories on different branches both append lines; git
  merges them trivially. Even if a textual conflict ever happens, any
  resolution is safe because import deduplicates by ID.
- **Import is idempotent.** `import_records` loads the set of existing
  memory IDs once, skips known ones, and tolerates corrupt lines with a
  warning. Running it a thousand times is the same as running it once.
- **Transport is automatic.** The watcher routes changes to this file to
  the importer, so a `git pull` that brings new lines is imported within
  seconds with no user action. Full sync and `dot init` import it too;
  `dot import` does it on demand.
- **Attribution travels.** Author is read from `git config user.name` at
  export time and becomes an `author:` tag on import, alongside a `shared`
  tag.

The complementary channel costs nothing: decisions mined from commit
messages are *already* identical across the team because their IDs are
derived from the commit itself (section 6.2). The JSONL file only carries
what git history cannot: manual captures and decisions recorded from AI
conversations.

`dot memory export` / `dot import <file>` round out portability: a plain
JSON export that can be moved between machines or backed up, importable
with the same idempotent machinery.

The deliberate non-goal: a central sync server. It would break local-first,
add an operational burden, and solve a problem (live sync of non-repo
artifacts) no user has hit yet.

## 14. Integrations

**Claude Code** (`dot/integrations/claude.py`). Three layers written by
init when enabled: the `.mcp.json` MCP registration (primary), a CLAUDE.md
section teaching Claude the REST endpoints (fallback and documentation),
and a SessionStart hook in `.claude/settings.json` that curls `/context`
when a session begins (best-effort, two-second timeout, never blocks the
session). Init only enables this when it detects Claude usage, or when
forced with `--claude`.

**Copilot** (`dot/integrations/copilot.py`). Copilot cannot call local
APIs, so there are two bridges. The VS Code extension
(`vscode-extension/`) is the rich path: it queries `/context` on every
editor switch, shows a "What Dot Knows" sidebar, registers a Language
Model tool (`dot-context_lookup`) that Copilot Chat can call, and offers a
capture-decision command. The zero-extension path maintains a marker
delimited section inside `.github/copilot-instructions.md` with the top
weighted decisions, refreshed hourly by the daemon, which Copilot reads
natively. Opt-in via `dot init --copilot`.

**Git** (`dot/integrations/git.py`). Beyond mining, this module reads
recent commits and branch state for `/status`, computes per-file churn and
author summaries, and installs the post-commit hook. The hook is a
two-line shell script that curls `/hooks/git/commit` and never fails the
commit (`|| true`); the 15-minute scheduled re-mine is the safety net for
anything the hook misses. The installer refuses to overwrite a pre-existing
hook it does not own.

## 15. Storage footprint

The question "will this exhaust my disk" deserves real numbers.

Per chunk costs:

| component | with ChromaDB | fallback mode |
|---|---|---|
| chunk text in SQLite | ~ size of the code itself | same |
| vector | 384 floats * 4 B ≈ 1.5 KB + HNSW overhead | ~8 KB as JSON text |
| metadata row | ~200 B | ~200 B |

Rules of thumb:

- A **small project** (100 files, ~500 chunks): about 1 to 5 MB. The
  demo projects in this repo's tests sit under 100 KB.
- A **large project** (4,000 files, ~12,000 chunks): roughly 30 to 60 MB
  with ChromaDB. The index is usually smaller than the project's own
  `.git` directory and far smaller than one `node_modules`.
- Memories are negligible: a few hundred bytes each, thousands of them fit
  in a megabyte.

One-time global costs, shared across all projects: the MiniLM model
(~90 MB in the HuggingFace cache) and PyTorch (a few hundred MB installed
with `[ml]`).

Growth is bounded by project size, not by time: re-indexing replaces a
file's chunks rather than appending, and the forgetting curve archives
stale memories. The only append-only artifact is `dot-memories.jsonl`,
which is human-scale text.

Verification and cleanup: `dot status` shows the exact size on the "local
storage" row; `rm -rf .dot` removes everything and `dot sync` rebuilds it.

## 16. Performance

- **Context assembly**: the target is under 100 ms and typical numbers are
  well under it (the header `x-dot-assembly-ms` reports per request).
  Cost breakdown: one query embedding (~10 ms CPU with MiniLM, microseconds
  with hashing), one ANN query (sub-millisecond with HNSW), three SQLite
  lookups, Python-side scoring of at most ~60 candidates.
- **Initial index**: dominated by embedding. MiniLM on CPU embeds roughly
  500 to 2,000 chunks per minute depending on hardware. A 12,000-chunk
  project takes minutes once, then never again in full.
- **Incremental update**: hash check (microseconds) + parse + embed only
  the changed file, typically tens of milliseconds plus embedding.
- **Memory (RAM)**: the daemon idles at roughly 150 to 400 MB with the
  model loaded; the hashing mode runs in a few tens of MB.

## 17. Privacy and security

- The API binds to 127.0.0.1 only; nothing is reachable from the network.
- No telemetry, no accounts, no cloud. The single outbound call ever is the
  one-time model download from HuggingFace (skippable by pre-seeding the
  cache or using hashing mode).
- All state is in two places you can see: `.dot/` in the project and
  `~/.dot/` for daemon bookkeeping. Deleting them deletes everything.
- Threat model note: any local process can query the localhost API, which
  matches the trust model of local development tools generally (your editor
  and shell already read the same files). An auth token is a possible
  future hardening, listed in section 19.
- The shared memories file is reviewed like any code change: it is plain
  text in the repo, visible in every PR diff.

## 18. Graceful degradation

| missing piece | what happens instead |
|---|---|
| sentence-transformers / torch | deterministic feature-hash embeddings; lexical rather than semantic matching |
| ChromaDB | embeddings stored in SQLite, brute-force cosine search |
| tree-sitter | Python via builtin `ast`; other languages via regex heuristics |
| git / not a repo | decision mining and hooks disabled, with an explicit warning at init |
| APScheduler | periodic jobs disabled, watcher and API still run |
| dashboard not built | `/ui` returns a friendly JSON hint instead of 404 |
| daemon not running | every CLI command falls back to an in-process engine |
| preferred port busy | next free port, persisted to project config |
| model download blocked | permanent in-process fallback to hashing, logged once |

The unifying rule: a missing optional dependency may reduce quality, never
availability.

## 19. Known limits and extension points

Honest list, ordered by how likely you are to hit them:

1. **Conversation capture is manual.** Nothing intercepts Copilot or Claude
   chats automatically; insights reach Dot only through `dot_remember`, the
   VS Code command, or `/memory/conversation`. Automatic capture is the
   biggest open product gap.
2. **Decision mining is pattern-based.** "chose X over Y because" is
   captured; a rationale phrased unusually is missed. A local small-model
   classifier is the natural upgrade and would still be local-first.
3. **Token estimation is approximate** (`len // 4`). Real tokenizers differ
   by language; budgets should be treated as targets, not guarantees.
4. **The heuristic parser is shallow** for non-Python languages without
   tree-sitter: no docstrings, estimated block ends.
5. **Embedding model changes invalidate the index** silently in terms of
   quality (old and new vectors are not comparable). Changing
   `embedding_model` should be followed by `dot sync --force`.
6. **No API auth token** (see section 17).
7. **Windows service installation** is manual (Task Scheduler); only
   launchd and systemd are generated.
8. **The dependency graph is import-based only**; it does not capture
   runtime relationships (DI containers, message queues, dynamic imports).

Good first extensions if you want to develop the system: an
`extra_ignored_globs` setting, an LLM-optional decision classifier behind
the existing `parse_decision` interface, a `dot doctor` diagnostic command,
and re-rendering CLAUDE.md when the resolved port changes.

---

## Appendix: file map

```
dot/
  config.py                project + global configuration, extension sets
  daemon.py                orchestration, scheduler, ports, pid files, services
  api.py                   FastAPI app, all REST endpoints
  cli.py                   Typer CLI, every command
  indexer/
    watcher.py             debounced filesystem watching, project walking
    parser.py              ast / tree-sitter / regex parsing, comment mining
    chunker.py             symbol-aligned chunking, token estimation
    embedder.py            MiniLM + hashing fallback, batching, cache
  memory/
    store.py               SQLite schema, ChromaDB, all persistence
    decisions.py           pattern mining, idempotent capture
    decay.py               forgetting curve, recency scoring
    shared.py              team shared memory: export, import, JSONL
  context/
    assembler.py           the gather/rank/budget algorithm
    ranker.py              scoring weights, proximity, deduplication
    formatter.py           claude / copilot / markdown / raw rendering
  integrations/
    git.py                 history, churn, blame, post-commit hook
    claude.py              CLAUDE.md, SessionStart hook, .mcp.json
    copilot.py             copilot-instructions.md maintenance
    mcp.py                 stdio JSON-RPC MCP server
vscode-extension/          sidebar, LM tool, decision capture, decorations
dashboard/                 React UI served at /ui
dot-site/                  the product website (Astro)
website/                   single-file landing page
```

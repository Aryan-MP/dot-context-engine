# Foundations: everything you need before reading internals.md

This document teaches the background concepts that `internals.md` assumes
you already know. It starts from zero on each topic, uses small examples
you can verify by hand, and ends every chapter with a note on exactly where
Dot uses that concept. Read this first, then internals.md, and the whole
system should feel obvious rather than magical.

No prior machine learning knowledge is assumed. High school math is enough.

## Contents

Part 1: Text and meaning
1. [Tokens: how machines measure text](#1-tokens)
2. [Vectors: turning anything into a list of numbers](#2-vectors)
3. [Similarity: cosine and the dot product](#3-similarity)
4. [Embeddings: vectors that capture meaning](#4-embeddings)

Part 2: The AI landscape Dot lives in
5. [LLMs, prompts, and the context window](#5-llms-and-context-windows)
6. [RAG: retrieval augmented generation](#6-rag)

Part 3: Core computer science
7. [Hash functions and content addressing](#7-hash-functions)
8. [Parsing and the abstract syntax tree](#8-parsing-and-asts)
9. [Databases: tables, transactions, indexes](#9-databases)
10. [Vector databases and nearest neighbor search](#10-vector-databases)

Part 4: The math Dot's formulas use
11. [Exponential decay and half-life](#11-exponential-decay)
12. [Logarithms for taming big numbers](#12-logarithms)
13. [Weighted sums: combining signals into one score](#13-weighted-sums)

Part 5: Systems programming
14. [Processes, daemons, and threads](#14-processes-daemons-threads)
15. [Filesystem events and debouncing](#15-filesystem-events)

Part 6: How programs talk to each other
16. [Ports, localhost, HTTP, and REST](#16-networking)
17. [JSON, stdin/stdout, and JSON-RPC](#17-json-and-json-rpc)

Part 7: Git, deeper than commands
18. [Git as a content-addressed database](#18-git-internals)

[Reading map: which chapter unlocks which part of internals.md](#reading-map)

---

# Part 1: Text and meaning

## 1. Tokens

Machines do not process text letter by letter or word by word. Language
models break text into **tokens**: pieces that are usually a bit smaller
than a word. "authentication" might become two tokens, `authent` and
`ication`. Common short words are one token. Code tokenizes a little
differently from prose because of symbols and casing.

Why you care about tokens at all: every language model has a maximum
number of tokens it can read at once (its context window, chapter 5), and
API pricing is per token. So when Dot promises "context within a 4,000
token budget", tokens are the currency being budgeted.

A useful rule of thumb: **one token is roughly 4 characters of English or
code**. So a 2,000 character function is about 500 tokens. This estimate
is wrong by maybe 10 to 15 percent either way, which is fine for
budgeting, and it costs nothing to compute.

**Where Dot uses this:** `estimate_tokens(text) = len(text) // 4` in
`dot/indexer/chunker.py`. Every budget decision in the context assembler
runs on this estimate. internals.md section 4.3 and 7.

## 2. Vectors

A **vector** is just an ordered list of numbers. The list `(3, 4)` is a
2-dimensional vector. You can picture it as an arrow from the origin of a
graph to the point x=3, y=4.

Two ideas transfer directly from this picture to everything Dot does:

**Length (magnitude).** By Pythagoras, the length of `(3, 4)` is
`sqrt(3² + 4²) = sqrt(25) = 5`. The same formula works in any number of
dimensions: square every component, sum, square root.

**Direction.** Two arrows can point the same way even if one is longer.
`(3, 4)` and `(6, 8)` point in exactly the same direction.

A vector with length 1 is called **normalized** or a **unit vector**. You
normalize by dividing every component by the length: `(3, 4)` becomes
`(0.6, 0.8)`. Normalizing throws away length and keeps only direction.

Now the leap: nothing stops a vector from having 384 dimensions instead
of 2. You cannot picture it, but all the math is identical: length is
still square-sum-root over 384 numbers, direction still means what it
means. When Dot embeds a function into "a 384-dimensional unit vector",
that is the whole content of the phrase: a list of 384 numbers, scaled to
length 1.

**Where Dot uses this:** every chunk and every memory is stored as a
384-dimensional vector. The number 384 comes from the embedding model
(chapter 4). internals.md sections 3 and 4.4.

## 3. Similarity

How similar are two vectors? The standard tool is the **dot product**:
multiply the vectors component by component and add it all up.

```
a = (1, 2)      b = (3, 1)
a · b = 1*3 + 2*1 = 5
```

The dot product has a beautiful geometric meaning:

```
a · b = |a| * |b| * cos(angle between a and b)
```

So if you divide the dot product by both lengths, you isolate the cosine
of the angle. That value is **cosine similarity**:

```
cos_sim(a, b) = (a · b) / (|a| * |b|)
```

Interpreting it:

| angle between vectors | cosine | meaning |
|---|---|---|
| 0° (same direction) | 1.0 | identical meaning |
| 90° (perpendicular) | 0.0 | unrelated |
| 180° (opposite) | -1.0 | opposite |

Work one example fully, by hand:

```
a = (1, 2)         |a| = sqrt(1 + 4)  = sqrt(5) ≈ 2.236
b = (2, 3)         |b| = sqrt(4 + 9)  = sqrt(13) ≈ 3.606
a · b = 1*2 + 2*3 = 8
cos_sim = 8 / (2.236 * 3.606) = 8 / 8.062 ≈ 0.992
```

Almost 1: these two arrows point nearly the same way. Now compare `a`
against `c = (3, -1)`:

```
a · c = 1*3 + 2*(-1) = 1
|c| = sqrt(10) ≈ 3.162
cos_sim = 1 / (2.236 * 3.162) ≈ 0.141
```

Nearly perpendicular, so nearly unrelated. The same arithmetic with 384
components is what Dot runs on every query.

One shortcut to remember: **if both vectors are already normalized, the
denominators are 1, so cosine similarity is just the dot product**. That
is why Dot normalizes embeddings at creation time: it turns every later
similarity check into a plain multiply-and-add.

**Where Dot uses this:** `cosine_similarity` in
`dot/indexer/embedder.py`; ChromaDB is configured with cosine space; the
similarity component is 45 percent of every chunk's ranking score.
internals.md sections 3, 5.2 and 8.

## 4. Embeddings

So far vectors were just numbers we made up. An **embedding model** is a
neural network trained to produce vectors where *direction encodes
meaning*: texts that mean similar things come out pointing in similar
directions, even when they share no words.

How is that possible? A sketch of the training process, because the
intuition matters:

1. Start with a neural network (specifically a small **transformer**, the
   same architecture family as LLMs) that maps any text to 384 numbers.
   Initially the outputs are garbage.
2. Feed it millions of *pairs* of texts that are known to be related: a
   question and its answer, a headline and its article, two duplicate
   forum questions. This kind of pair data exists at internet scale.
3. After each batch, nudge the network's internal weights so that related
   pairs land closer together (higher cosine) and unrelated, randomly
   matched texts land further apart. This push-together pull-apart scheme
   is called **contrastive learning**.
4. Repeat until the geometry of the output space mirrors the semantics of
   language: "charge a credit card" and `def authorize(amount,
   card_token)` end up neighbors because, across millions of examples,
   texts like them co-occurred.

The model Dot uses, **all-MiniLM-L6-v2**, is a 6-layer transformer
distilled (compressed) from a larger model, about 90 MB, outputs 384
dimensions, and runs comfortably on a CPU. That last property is what
makes a local-first product possible: no GPU, no API.

Important practical consequences:

- **Embeddings are model-specific.** Vectors from two different models
  live in different spaces; comparing them is meaningless. This is why
  changing `embedding_model` in Dot's config requires re-indexing.
- **An embedding is a lossy summary.** You cannot recover the text from
  the vector. That is also why Dot stores the chunk text in SQLite
  alongside the vector: the vector finds, the text delivers.
- **Embedding a 1,000 line file produces mush.** The vector averages
  everything in the text, so the sharper the input, the sharper the
  geometry. This single fact motivates Dot's whole chunking design.

And the fallback, demystified: Dot's no-ML mode builds vectors by
**feature hashing**. Take every identifier-like token in the text, hash
it (chapter 7) to pick one of 384 slots and a +1 or -1 sign, add it in,
normalize at the end. Two texts that share many tokens then share many
slot contributions, so their cosine is high. It is "bag of words wearing
a vector costume": real lexical overlap, zero semantics, zero
dependencies, fully deterministic. Knowing this, you know exactly what
quality you give up by skipping the `[ml]` extra.

**Where Dot uses this:** `dot/indexer/embedder.py` end to end.
internals.md sections 3 and 4.4.

---

# Part 2: The AI landscape Dot lives in

## 5. LLMs and context windows

A **large language model** is a transformer trained on enormous text
corpora to predict the next token. Chat assistants, Copilot completions,
and Claude Code are all this mechanism with different wrappers.

The two properties that define Dot's reason to exist:

**LLMs are stateless.** The model has no memory between calls. What looks
like a conversation is the client resending the entire chat history with
every message. Close the chat, and that history is gone. Nothing about
your project persists anywhere inside the model.

**LLMs have a context window.** Each call can include at most N tokens of
input (tens of thousands to a few hundred thousand, depending on the
model). Your whole codebase does not fit, and even when it nearly fits,
stuffing it in is slow, expensive, and degrades the model's focus.

Put together: every AI session starts blank, and you can only give it a
limited briefing. So the engineering question becomes: **of everything I
know about this project, which few thousand tokens are the most useful
right now?** That question is precisely what Dot's context assembler
answers, and the "token budget" in Dot is a budget against this window.

A note on the word **prompt**: everything sent to the model in one call
(instructions, context, the user's question) is the prompt. When Dot
"injects context", it means: contribute a well-chosen block of text into
that prompt before the model runs.

**Where Dot uses this:** the entire product premise. internals.md
sections 1 and 7.

## 6. RAG

**Retrieval Augmented Generation** is the standard industry pattern for
the problem above:

1. Ahead of time: split your documents into chunks, embed each chunk,
   store the vectors in a searchable index.
2. At question time: embed the question, find the chunks whose vectors
   are most similar, paste those chunks into the prompt, let the LLM
   answer grounded in them.

The model does the *generation*; the *retrieval* supplies it facts it was
never trained on. This is how chatbots answer questions about your
private wiki.

Dot is recognizably RAG-shaped, and internals.md (section 3) lists the
four places it deliberately departs from the vanilla recipe. With this
chapter you can now read that list critically:

- vanilla RAG chunks by fixed token count; Dot chunks by code structure
  (chapter 8 explains the machinery),
- vanilla RAG ranks by similarity alone; Dot blends five signals
  (chapter 13 explains how blending works),
- vanilla RAG has one kind of content; Dot adds a second channel,
  decisions, with its own lifecycle (chapter 11 explains the decay math),
- vanilla RAG ingests once; Dot re-indexes continuously (chapter 15
  explains how it notices changes).

One more distinction worth internalizing: **Dot never calls an LLM.** It
is the retrieval half only, serving whichever model your tools already
use. That is what "model-agnostic" means concretely.

**Where Dot uses this:** internals.md sections 3 and 7.

---

# Part 3: Core computer science

## 7. Hash functions

A **hash function** takes any input bytes and produces a fixed-size
number, deterministically. SHA-256, the one Dot uses, outputs 256 bits,
usually shown as 64 hex characters:

```
sha256("hello")  = 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
sha256("hello!") = ce06092fb948d9ffac7d1a376e404b26b7575bcc11ee05a4615fef4fec3a308b
```

Three properties make hashes a structural tool, not just a checksum:

1. **Deterministic**: same input, same output, on any machine, forever.
2. **Avalanche**: change one character and the output is completely
   different (compare the two hashes above).
3. **Collision resistant**: you will never find two different inputs with
   the same SHA-256 output in practice.

Together these enable **content addressing**: use the hash *of a thing*
as the *identity of that thing*. The ID is then not assigned, it is
derived, and that has two superpowers:

- **Change detection for free.** Dot stores the hash of each file. On the
  next sync, hash the file again: same hash, provably same content, skip
  all work. This one comparison is why re-syncs are nearly instant.
- **Idempotency for free.** Dot's mined decisions get the ID
  `sha256(commit_source :: content)`. Mine the same git history twice, or
  on two different machines, and you derive the *same IDs*, so a "create
  if absent" write can never duplicate anything. The entire team-sharing
  design (conflict-free merges of `dot-memories.jsonl`) rests on this.

That word, **idempotent**: an operation you can run any number of times
with the same result as running it once. Whenever internals.md says
"idempotent import", translate it to "safe to re-run blindly", and
whenever you wonder why it is safe, the answer is content-addressed IDs.

**Where Dot uses this:** file hashes (`index_file`), chunk IDs
(`chunker.py`), memory IDs (`decisions.py`), the embedding cache key
(`embedder.py`), per-project PID file names (`daemon.py`). internals.md
sections 4, 6.2 and 13.

## 8. Parsing and ASTs

To a text editor, source code is a string. To do anything intelligent
with it, you need its **structure**, and the structure of code is a tree.

```python
def add(a, b):
    """Add two numbers."""
    return a + b
```

A parser reads this and produces an **abstract syntax tree (AST)**:

```
FunctionDef  name="add"
├── arguments: a, b
├── docstring: "Add two numbers."
└── Return
    └── BinOp
        ├── left: Name "a"
        ├── op: Add
        └── right: Name "b"
```

"Abstract" means details that do not affect meaning (whitespace, comment
placement, parenthesization style) are dropped. What remains is the
program as the language defines it: this file *contains a function named
add, spanning lines 1 to 3, with this docstring*.

Why Dot needs ASTs rather than string tricks: the chunker must know
*exactly* where each function and class begins and ends, so that one
chunk equals one complete semantic unit. Cutting code every 500 tokens
would slice functions in half; the AST gives precise boundaries.

The three parsing strategies in Dot, in terms you now have:

1. **Python's `ast` module**: Python parses itself; the standard library
   hands you the real tree. Exact, free, Python-only.
2. **tree-sitter**: a parser generator with grammars for 30+ languages,
   producing real syntax trees fast. An optional dependency because its
   compiled grammars are heavyweight.
3. **Regular expressions**: pattern matching over the raw string.
   A **regex** like `def\s+(\w+)\(` means "the text `def`, whitespace, a
   captured word, an open paren", which finds Python function headers
   without understanding anything. Dot's fallback uses such patterns for
   functions, classes and imports, plus brace counting to guess where
   blocks end. Shallow, sometimes wrong, never unavailable.

**Where Dot uses this:** `dot/indexer/parser.py` is exactly these three
strategies; the chunker consumes the symbols they emit. internals.md
sections 4.2 and 4.3.

## 9. Databases

A **relational database** stores data in tables of rows and columns, and
**SQL** is the language for reading and writing it. **SQLite** is a full
relational database in a single file, no server process, accessed as a
library. It is the most deployed database on earth (every phone and
browser embeds it) and is ideal for local-first software: your index is
one file you can copy, inspect, or delete.

Concepts internals.md leans on:

**Schema**: the declared shape of the tables. Dot's four tables (chunks,
files, dependencies, memories) are the schema; section 5.1 lists their
columns.

**Primary key**: a column whose value uniquely identifies a row, e.g.
`chunk_id`. An **upsert** is "insert, or update if that key exists",
which combined with content-addressed IDs (chapter 7) gives idempotent
writes.

**Index**: a sorted lookup structure the database maintains on a column
so that finding rows by that column is fast (like a book index, versus
reading every page). Dot indexes columns it filters by, such as
`file_path` and `updated_at`.

**Transaction**: a group of writes that becomes visible all together or
not at all (atomicity). Dot wraps "delete this file's old chunks, insert
the new ones, update the file record" in one transaction, so a crash in
the middle cannot leave half-updated state. When internals.md says the
write path is "transactional", this is the guarantee being claimed.

**ORM** (object-relational mapper): a library that maps table rows to
language objects so you write Python instead of raw SQL strings. Dot uses
SQLAlchemy; the classes `ChunkRecord`, `MemoryRecord` and friends in
`store.py` are table definitions in Python clothing.

**Where Dot uses this:** `dot/memory/store.py` throughout. internals.md
section 5.1.

## 10. Vector databases

Relational databases answer "rows where x = value" superbly, but the
query Dot needs is different: *given this 384-dimensional vector, which
stored vectors have the highest cosine similarity?* That is **nearest
neighbor search**.

The honest baseline is **brute force**: compute the similarity against
every stored vector, sort, take the top k. For n vectors of dimension d,
that is n*d multiplications. With 10,000 chunks and 384 dimensions, about
4 million multiply-adds, a few hundred milliseconds in Python. Perfectly
usable, and exactly what Dot's fallback mode does.

To go faster, vector databases use **approximate nearest neighbor (ANN)**
indexes that trade a sliver of accuracy for orders of magnitude of speed.
The dominant structure, used by ChromaDB, is **HNSW** (hierarchical
navigable small world). The intuition without the math:

- Build a graph where each vector is a node connected to its near
  neighbors, plus a few long-range shortcut edges, arranged in layers
  like a highway system: sparse fast layers on top, dense local layers
  below.
- To search, start at the top layer, greedily hop to whichever neighbor
  is closest to the query, drop a layer when you stop improving, repeat.
  You descend from highways to streets to the right doorstep.
- Cost is roughly logarithmic in n rather than linear, and recall (the
  fraction of true neighbors found) is typically 95 percent or more.

"Approximate" deserves emphasis: HNSW may occasionally miss a true top-k
neighbor. For Dot this is harmless, because similarity is only 45 percent
of the final ranking anyway; a 96th-best-instead-of-95th-best candidate
does not change what fits a 4,000 token budget.

One more term: ChromaDB returns **distance** (lower is closer) while
Dot's ranking wants **similarity** (higher is closer); for cosine they
interconvert as `similarity = 1 - distance`. That explains the one-liner
in the store.

**Where Dot uses this:** `_ChromaBackend` and `_brute_force` in
`dot/memory/store.py`. internals.md section 5.2.

---

# Part 4: The math Dot's formulas use

## 11. Exponential decay

Many natural processes lose a constant *fraction* per time period rather
than a constant amount. The clean way to express that is half-life: the
time for a quantity to halve. The formula:

```
value(t) = initial * 2^(-t / half_life)
```

Check it against intuition with a 30 day half-life:

| t | 2^(-t/30) | value |
|---|---|---|
| 0 days | 2^0 | 1.000 |
| 30 days | 2^-1 | 0.500 |
| 60 days | 2^-2 | 0.250 |
| 90 days | 2^-3 | 0.125 |
| 365 days | 2^-12.2 | 0.0002 |

Two properties matter for Dot:

- **Never zero, smoothly.** Unlike a hard cutoff ("delete memories older
  than 90 days"), decay ranks a 31-day-old memory just slightly below a
  29-day-old one. No cliff, no arbitrary boundary.
- **One tunable knob with physical meaning.** "Memories halve in
  relevance monthly" and "code recency halves every 3 days" are
  statements a human can sanity-check, and both are config values.

Dot applies the same curve twice at different time scales: memory weight
(half-life 30 days, internals section 6.3) and code recency (half-life 72
hours, the recency component of ranking, section 8). When you read the
memory weight formula

```
weight = confidence * 2^(-age/half_life) * (1 + 0.25 * ln(1 + accesses))
```

you now recognize the middle factor exactly; the last factor is next
chapter.

**Where Dot uses this:** `dot/memory/decay.py`. internals.md sections 6.3
and 8.

## 12. Logarithms

The natural logarithm `ln(x)` answers "e to what power gives x". For
intuition you only need its shape: **it grows fast at first and then very
slowly**. ln(1)=0, ln(3)≈1.1, ln(10)≈2.3, ln(100)≈4.6. Multiplying the
input by 10 only *adds* about 2.3 to the output.

That shape is precisely the tool for "more is better, but with rapidly
diminishing returns", and Dot reaches for it twice:

**Edit frequency.** A file edited 20 times is more load-bearing than one
edited twice, but a file edited 200 times is not 10 times more important
than the 20-edit file. Dot scores it as `ln(1 + edits) / ln(50)`, capped
at 1. The `1 +` (the `log1p` you will see in code) just makes zero edits
give exactly zero. Spot values: 0 edits → 0, 7 edits → 0.53, 20 edits →
0.78, 49 edits → 1.0, and everything past 49 stays 1.0.

**Memory reinforcement.** Each retrieval of a memory bumps its access
count, and the weight formula multiplies by `1 + 0.25 * ln(1 + accesses)`.
First few uses help a lot (10 accesses → factor 1.60); the next hundred
help only a little (100 accesses → 2.15). So frequent use keeps a memory
warm but can never make it immortal: decay's exponential eventually beats
reinforcement's logarithm, which is the designed outcome.

**Where Dot uses this:** `edit_frequency_score` in
`dot/context/ranker.py` and the reinforcement term in
`dot/memory/decay.py`. internals.md sections 6.3 and 8.

## 13. Weighted sums

The simplest way to combine several signals into one number is a
**weighted sum**: score each signal between 0 and 1, multiply each by a
weight expressing how much you trust it, add. If the weights sum to 1,
the result is also between 0 and 1.

This is exactly a weighted average, the same arithmetic as a course
grade: 45 percent final exam, 20 percent each for two midterms, 10
percent homework, 5 percent participation. Dot's chunk ranking *is* that
grade sheet:

```
score = 0.45 * similarity
      + 0.20 * proximity
      + 0.20 * recency
      + 0.10 * edit_frequency
      + 0.05 * tag_boost
```

Two things to understand about this technique:

**The weights encode a worldview, not a theorem.** 0.45 for similarity
says "what the text means is the strongest signal, but a majority of the
judgment is context: where you are, what is fresh, what gets touched".
There is no proof these are optimal; they are sensible defaults that a
fork could tune, and internals.md section 8 shows with a worked example
what behavior they produce (a fresh related file outranking a stale but
textually closer document).

**Inputs must be normalized first.** A weighted sum is only meaningful if
every signal lives on the same 0-to-1 scale. That is the hidden job of
chapters 11 and 12: the decay curve squashes "age in hours" to 0..1, the
log squashes "edit count" to 0..1, cosine already lands in -1..1 and is
clamped at 0. Each signal is tamed individually, then they are blended.

**Where Dot uses this:** `score_chunk` in `dot/context/ranker.py`, and a
softer variant for memories (`similarity * (0.5 + 0.5 * weight)`).
internals.md section 8.

---

# Part 5: Systems programming

## 14. Processes, daemons, threads

A **process** is a running program with its own memory, identified by a
**PID** (process ID). Your shell, your editor, and each `python` you
launch are separate processes.

A **daemon** is a process designed to run in the background for a long
time, detached from any terminal, doing work on events and timers rather
than direct user commands. Web servers, sync clients, and Dot are
daemons. The practical questions every daemon must answer, and where Dot
answers them:

- *How do I find it later to stop it?* Write the PID to a known file at
  startup (a **PID file**); `dot daemon stop` reads it and sends the
  process a termination **signal** (SIGTERM), which the daemon catches to
  shut down cleanly. internals.md section 10.
- *How does it survive reboots?* Register with the operating system's
  service manager: **systemd** on Linux, **launchd** on macOS. Dot writes
  those unit files for you.

A **thread** is a unit of execution *inside* a process. Threads share the
process's memory, which is powerful and dangerous: two threads writing
the same data concurrently produce a **race condition**, where the
result depends on accidental timing. The defense is a **lock** (mutex):
a token only one thread can hold; others wait. Inside Dot's daemon, the
watcher thread and the sync thread can both try to write the store, so
writes happen under an index lock. The embedder's model loading uses a
lock too (so two threads do not load a 90 MB model twice), in a pattern
called double-checked locking: check, lock, check again, act.

A **background job scheduler** (Dot uses APScheduler) is just a thread
that wakes on a timer and runs registered functions: re-mine git every 15
minutes, prune decayed memories every 6 hours.

**Where Dot uses this:** `dot/daemon.py` for all of it. internals.md
section 10.

## 15. Filesystem events

Operating systems can notify a program when files change (inotify on
Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows). The Python
library **watchdog** wraps all three behind one API. This is push, not
poll: instead of rescanning the disk every second, the program sleeps
until the OS says "this path changed".

The catch is that raw events are *noisy*. One save in a modern editor can
emit half a dozen events: editors write to a temp file, flush, rename
over the original, and a formatter may rewrite the file again
immediately. Reacting to each event would re-index the same file six
times in one second.

The standard fix is **debouncing**: when an event arrives, do not act;
start (or reset) a short countdown for that path, and only act when the
countdown expires with no new events. The name comes from mechanical
switches, whose contacts physically bounce and close several times per
press; circuits ignore the bounces and register one press. Dot's debounce
window is 1.5 seconds: a burst of writes collapses to one indexing pass,
at the cost of a 1.5 second delay nobody notices.

(The same idea appears all over software: search boxes that wait for you
to stop typing before querying are debouncing keystrokes.)

**Where Dot uses this:** `ProjectWatcher` in `dot/indexer/watcher.py`,
with the pending-map-plus-flusher-thread implementation. internals.md
sections 2 and 4.1.

## 16. Networking

When two programs on the *same machine* need to talk, the common
mechanism is still networking, just aimed inward.

**localhost / 127.0.0.1** is a special address meaning "this machine".
Traffic to it never touches any network hardware; the operating system
loops it back internally. A server bound to 127.0.0.1 is therefore
physically unreachable from other computers. This single line is most of
Dot's security story.

A **port** is a number (1 to 65535) that distinguishes the many servers
one machine may run: the address says which machine, the port says which
program. Only one program can listen on a given port at a time, which is
why two Dot daemons cannot both have 7337, and why Dot probes upward
(7338, 7339...) until it finds a free one.

**HTTP** is the request/response protocol of the web: a client sends a
method (GET to read, POST to create, DELETE to remove), a path
(`/context`), optional query parameters (`?query=auth&fmt=claude`) and
body; a server replies with a status code (200 ok, 404 not found, 422
invalid input) and a body. **REST** is the design convention of using
those methods and paths to model resources, which is why Dot's API reads
as nouns: `/memory`, `/graph`, `/status`.

So "Dot exposes a REST API on localhost:7337" decodes to: a program on
your machine, listening inward only, on door number 7337, speaking
standard HTTP, which is exactly why *any* tool (curl, a VS Code
extension, a Python script) can integrate with it without an SDK.

**Where Dot uses this:** `dot/api.py` (FastAPI is a Python framework that
turns functions into HTTP endpoints; uvicorn is the server that runs it).
internals.md sections 10, 11 and 17.

## 17. JSON and JSON-RPC

**JSON** is the universal text format for structured data: objects in
braces, arrays in brackets, strings, numbers, booleans.

```json
{"kind": "decision", "confidence": 0.95, "tags": ["storage"]}
```

**JSONL** (JSON Lines) is simply one JSON object per line of a file. Its
virtue is appendability: adding a record is appending a line, no parsing
or rewriting of what exists. Combined with git, it has a second virtue:
line-based diffs and merges work naturally. Two branches each appending
different lines merge cleanly. This is why `dot-memories.jsonl` is JSONL
and append-only rather than one big JSON document, which would conflict
on every concurrent edit.

**stdin and stdout** are the text channels every process is born with:
one for input, one for output. Two processes can be wired together so
that one's stdout is the other's stdin; no network, no ports, and the
child process dies with its parent. For a tool that should run *per
project, on demand, with zero setup*, this beats running a server.

**JSON-RPC** is a tiny protocol for calling functions across such a
channel: each request is a JSON object with a `method`, `params`, and an
`id`; each response carries the same `id` with a `result` or an `error`.
A request *without* an id is a **notification**: fire-and-forget, no
response expected, by the spec.

```
→ {"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"dot_status"}}
← {"jsonrpc":"2.0","id":7,"result":{...}}
```

**MCP** (Model Context Protocol) is a standard built on newline-delimited
JSON-RPC over stdio, defining the conversation between an AI client
(like Claude Code) and a tool server: a handshake (`initialize`), tool
discovery (`tools/list`, returning each tool's name, description, and
JSON schema of its arguments), and invocation (`tools/call`). The model
reads the tool descriptions and decides when to call them. With this
chapter, the protocol walkthrough in internals.md section 12 is fully
readable, including details like "stdout belongs to the protocol, logs
must go to stderr" (anything else printed to stdout would corrupt the
JSON stream).

**Where Dot uses this:** `dot/integrations/mcp.py` (the protocol),
`dot/memory/shared.py` (JSONL). internals.md sections 12 and 13.

## 18. Git internals

You use git daily; two of its internal ideas explain why Dot leans on it
so hard.

**Git is a content-addressed database.** Every commit is identified by
the SHA-1 hash of its content (tree, parents, author, message,
timestamps). Chapter 7's logic applies wholesale: the commit `e76402d` is
the same object on your machine and every teammate's, bit for bit,
guaranteed by its hash. So when Dot derives a memory's ID from a commit,
that ID is *globally* stable: every machine that mines the commit
derives the same memory. Team convergence is not a synchronization
feature Dot built; it is a property inherited from git's design.

**Commit messages are a decision journal nobody reads.** The discipline
of writing "Chose Redis over Memcached because of TTL requirements"
exists in good teams, and git preserves it forever, but no tool surfaces
it at the moment you need it. Dot's miner (pattern matching over
messages, internals 6.2) is an attempt to read the journal back.

Two mechanical features Dot uses:

**Hooks**: executable files in `.git/hooks/` that git runs at lifecycle
points. `post-commit` runs after each commit; Dot installs a two-line
script there that pings the daemon, turning "commit made" into "decision
mined" within seconds. A hook that fails must not break the commit,
hence the `|| true`.

**The repo as transport**: push and pull move content between machines
with authentication, history, and review already solved. Any file
committed to the repo rides this channel, which is the entire mechanism
behind `dot-memories.jsonl`: Dot did not build sync, it parked a file on
rails that already existed.

**Where Dot uses this:** `dot/integrations/git.py`,
`dot/memory/decisions.py`, `dot/memory/shared.py`. internals.md sections
6.2, 13 and 14.

---

# Reading map

Which chapters unlock which sections of internals.md:

| internals.md section | prerequisite chapters |
|---|---|
| 1. Problem and principles | 5, 6 |
| 2. Life of a file save | 7, 8, 14, 15 |
| 3. Concepts primer | 1, 2, 3, 4 (it will now read as revision) |
| 4. Indexing pipeline | 1, 7, 8, 15 |
| 5. Storage | 9, 10 |
| 6. Memory and decay | 7, 11, 12 |
| 7. Context assembly | 1, 5, 6 |
| 8. Ranking math | 3, 11, 12, 13 |
| 9. Formatters | 5 |
| 10. The daemon | 14, 16 |
| 11. REST API | 16, 17 |
| 12. MCP server | 17 |
| 13. Team shared memory | 7, 17, 18 |
| 14. Integrations | 16, 17, 18 |
| 15. Storage footprint | 2, 9 |
| 16. Performance | 10, 14 |
| 17. Privacy | 16 |
| 18. Degradation | 4, 8, 10 |

A suggested path for one sitting: read Parts 1 and 2 of this document
(the conceptual core), skim Parts 3 to 7 stopping wherever something is
new to you, then read internals.md top to bottom. Where internals states
a fact ("imports are idempotent", "cosine is just the dot product here",
"the merge is conflict-free"), you should now be able to supply the
*because* yourself. That is the test of ownership.

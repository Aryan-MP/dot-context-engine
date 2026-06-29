# Your AI tools have amnesia. I built them a shared memory.

I have a small confession: I got tired of explaining my own codebase to robots.

I use a few AI coding tools every day. Claude Code in the terminal, sometimes the
Claude Code app, GitHub Copilot in my editor, and an open-source model in a side
session when I want a second opinion. They are all useful. They are also all
amnesiacs. I would explain my architecture to one, then explain the same thing to
the next, then explain it again in a fresh chat the next morning. Every decision I
made, and every reason behind it, lived in my head and nowhere else.

So over a few weekends I built a small thing to fix it for myself. I call it Dot.

This is a walkthrough of what it is and how to set it up, on both the terminal and
in VS Code, ending with the demo that made me think it was worth sharing.

## What Dot is, in three sentences

Dot is a local daemon that acts as a shared memory for all your AI tools. It
quietly learns your codebase and, more importantly, the *why* behind it: the
decisions, the rejected alternatives, the "we chose X over Y because" that usually
evaporates when a chat ends. Any tool can read from it and write back to it, so
what one agent learns, every agent knows.

Everything runs on your machine. No code leaves your laptop, there is no account,
and there is no cloud. Embeddings are generated locally, storage is SQLite plus a
local vector index on disk.

## Before you start

You need Python 3.11 or newer. That is the only requirement.

## Path 1: the terminal

Install it from PyPI. The `[ml]` extra pulls in the local embedding model, which is
what makes search understand meaning instead of just matching words:

```bash
pip install "dot-context[ml]"
```

Now go into a real project. The experience is far more convincing on a codebase with
months of real git history than on a toy folder:

```bash
cd ~/code/your-project
dot init --claude --copilot
```

`dot init` does a few things in order: it indexes your code (parsed into functions
and classes, not blind token windows), mines your last 500 commits for decisions,
installs a git hook so future commits are captured automatically, and wires up the
tools you asked for. Then start the background daemon:

```bash
dot daemon start
dot status
```

`dot status` should show files indexed greater than zero and the daemon running.
Note the port it prints (7337 by default). Every tool will talk to the daemon on
that port.

Now the first real test. Ask it something in plain language:

```bash
dot ask "how do we handle authentication"
```

If Dot returns the files that actually implement auth, even ones that never use the
word "authentication," semantic search is working. That single result is the whole
argument for the local embedding model.

You can also print assembled context and pipe it anywhere:

```bash
dot inject "refactoring the billing module" --fmt claude
```

## Path 2: VS Code and Copilot

Download the `.vsix` from the latest GitHub release and install it:

```bash
code --install-extension dot-context.vsix
```

Once installed you get three things:

1. A sidebar panel called "What Dot Knows" that shows the context and decisions
   relevant to the file you are looking at.
2. A Copilot Chat tool. Type `#dotContext` in a Copilot Chat message and your
   question is answered with your project's real context attached.
3. Command-palette actions: "Dot: Capture Decision" to record a decision on the
   spot, plus "Dot: Show Context" and "Dot: Sync".

If you also use Claude Code, `dot init --claude` already registered Dot as an MCP
server, so Claude Code can call three native tools: `dot_context` to pull context,
`dot_remember` to record a decision, and `dot_status` to check health. You can
literally tell it "record in dot: we chose advisory locks over Redis for dedup" and
it will.

## The payoff: one memory, every tool

Here is the demo that sold me on it. The rule that makes it work: open every tool on
the same project folder, so they all talk to the same daemon.

First, record a decision once, from the terminal:

```bash
dot memory add "Chose Postgres advisory locks over Redis for job dedup, one less service to run"
```

Now read it back from somewhere completely different. From any other tool, editor,
script, or a side session running an open-source model:

```bash
curl 'http://127.0.0.1:7337/context?query=how%20do%20we%20dedup%20jobs&fmt=raw'
```

The decision is right there in the response, alongside the relevant code. Open a
fresh Claude Code session and ask "how do we dedup jobs?" and it knows, because the
context was injected at the start. Type `#dotContext how do we dedup jobs` in Copilot
and it knows too.

No re-explaining. No copy-pasting context between tools. You taught one tool, and
every tool learned. That is the entire point.

## How it works, briefly

Two ideas are worth understanding, because they are the interesting part.

The first is ranking. When you ask for context, Dot does not just return the nearest
vectors. It blends several signals: semantic similarity to your query, how close a
chunk is to the file you are working in, how recently it changed, how often it
changes, and whether it carries a decision tag. Then it fills a token budget greedily
from the top. The result is context that respects what you are actually doing right
now, not just what is textually similar.

The second is forgetting. Memories lose weight as they age, but every time one gets
pulled into context it is reinforced. A decision you keep using stays sharp; a stale
one fades and is eventually archived. It is spaced repetition, applied to a codebase.

## Honest limits

It is early, and I would rather you know the rough edges than discover them.

Decision mining from commits and comments is heuristic right now, so it catches
clearly phrased rationale ("chose X over Y," "decided to," "workaround for") and
misses decisions buried in vague messages. The shared memory is real, but a running
Claude Code session only picks up new memories at session start, so you start a fresh
session or call `dot_context` to see something you just recorded. And it is an alpha,
so expect sharp corners.

None of that changes the core, which already works: a single, local, private memory
that every one of your AI tools can share.

## Try it

If you also live with three AI tools that never talk to each other, maybe it helps
you too. It is open source under the MIT license.

- Code and full docs: https://github.com/Aryan-MP/dot-context-engine
- The complete walkthrough with thirteen verifiable experiments lives in
  `docs/getting-started.md` in the repo.

I would genuinely love feedback, gentle or brutal. And I would be happy if it helped
even one person stop repeating themselves to a machine.

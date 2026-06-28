# Dot — Launch post (Product Hunt)

## Tagline

A local-first memory layer that teaches every AI tool your codebase.

## Description

Every AI session starts from zero. You explain your architecture to Claude Code, then again to Copilot, then again in a new chat. Dot ends that loop.

Dot is a local daemon that watches your project, indexes code semantically, mines architectural decisions from git history and Claude Code transcripts, and serves ranked context to any AI tool through `http://127.0.0.1:7337`. No code leaves your machine.

## Key features

- **Local-first**: embeddings on CPU, storage in SQLite + ChromaDB
- **Model-agnostic**: Claude Code, Copilot, Cursor, custom scripts — anything that can hit localhost
- **Decision memory**: captures "we chose X over Y because..." from commits and conversations
- **VS Code integration**: sidebar + Copilot Chat tool (`#dotContext`)
- **Open source**: MIT, built in Python + TypeScript

## Links

- Website: https://dot-context-engine.vercel.app
- GitHub: https://github.com/Aryan-MP/dot-context-engine
- PyPI: https://pypi.org/project/dot-context/
- VS Code Marketplace: https://marketplace.visualstudio.com/items?itemName=AryanMangod.dot-context-memory

## Maker comment

I built Dot because I was tired of re-explaining the same codebase to every AI tool. The first time feels magical: open a new Claude Code session, ask something vague like "how does auth work here," and it already knows.

## Tags

developer-tools, ai, open-source, productivity, machine-learning

# Contributing to Dot

Thanks for taking the time to contribute! Dot is an open-source, local-first AI context
memory daemon. All contributions - bug reports, documentation fixes, feature ideas, and
pull requests - are welcome.

## Getting started

1. Fork the repository and clone your fork.
2. Create a virtual environment (Python 3.11+).
3. Install in editable mode with dev extras:

```bash
pip install -e ".[dev]"
```

For the full ML stack (local embeddings):

```bash
pip install -e ".[ml]"
```

## Development workflow

```bash
make test        # run pytest
make lint        # run ruff
make typecheck   # run mypy (optional)
```

Please make sure tests pass and the code is linted before opening a PR.

## Project layout

```
dot/              # core Python package
  indexer/        # code parsing, chunking, embedding
  memory/         # decision store, decay, shared memory
  context/        # context assembly, ranking, formatting
  integrations/   # Claude, Copilot, git, MCP wiring
  conversations/  # transcript capture
  doctor.py       # first-run health checks
tests/            # pytest suite
vscode-extension/ # VS Code extension (TypeScript)
dashboard/        # web UI (React + Vite)
docs/             # MkDocs documentation
website/          # product website
dot-site/         # additional site assets
```

## How to contribute

1. **Open an issue first** for significant changes so we can agree on direction.
2. **Create a branch** from `main` with a descriptive name.
3. **Make focused commits** with clear messages.
4. **Add tests** for new behavior.
5. **Update documentation** if you change user-facing behavior.
6. **Open a pull request** and fill out the template.

## Commit message style

We use conventional commits:

```
feat: add conversation capture for Claude Code transcripts
fix: handle empty git repositories in doctor
docs: update getting started examples
ci: update release workflow
```

## Reporting bugs

When reporting a bug, please include:

- Your operating system and Python version.
- The version of `dot-context` you are running.
- Steps to reproduce.
- Expected vs actual behavior.
- Relevant logs or error messages.

## Suggesting features

Feature requests are best submitted as GitHub issues. Describe the problem you are trying
to solve, the use case, and any ideas you have for implementation.

## Code of conduct

Be respectful, constructive, and inclusive. We want Dot to be a welcoming project for
everyone.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Dot context memory

This project runs [Dot](https://github.com/aryanp-spektra/dot-context-engine),
a local context daemon. Query it for relevant code and past decisions:

- `curl 'http://127.0.0.1:7337/context?query=<your question>&fmt=claude'`
- `curl 'http://127.0.0.1:7337/memory'` — captured architectural decisions
- `curl -X POST http://127.0.0.1:7337/memory -H 'content-type: application/json' \
   -d '{"content": "<decision>", "kind": "decision"}'` — record a new decision

Record significant architectural decisions to Dot when you make them.

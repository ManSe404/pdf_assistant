# pdf_assistant documentation

pdf_assistant is a conversation with one PDF: answers cite the page they come from, and every
conversation is also a small experiment that users' votes steer. It is frozen as a demo. The
top-level [README](../README.md) says how to run it in five minutes. These pages say how it works.

## Reading order

| # | Document | Read it when you want | Status | Last checked |
|---|---|---|---|---|
| 1 | [Vision](product/vision.md) | what it is, for whom, its status and what the demo shows | current | 2026-11-11 |
| 2 | [Architecture overview](architecture/overview.md) | the one process, an upload and a question hop by hop, the experiment, accounts, data, tracing | current | 2026-11-11 |
| 3 | [Diagrams](diagrams/context.md) | the C4 [context](diagrams/context.md) and [container](diagrams/container.md) views | current | 2026-11-11 |
| 4 | [ADR 0001: rewrite on FastAPI without LangChain](adr/0001-rewrite-on-fastapi.md) | why the 2024 version was rewritten and what was kept | accepted | 2026-11-11 |
| 5 | [Setup](guides/setup.md) | to run it locally, in Docker, through Ollama, with Supabase or Pinecone | current | 2026-11-11 |
| 6 | [Development](guides/development.md) | the checks, the tests and the live end-to-end run | current | 2026-11-11 |
| 7 | [Configuration](reference/configuration.md) | every setting with its default | current | 2026-11-11 |
| 8 | [HTTP API](reference/api.md) | every route and the answer stream | current | 2026-11-11 |
| 9 | [Codebase](reference/codebase.md) | the file map and the dependencies | current | 2026-11-11 |

## Other files here

- `demo/`: the static interactive demo, published with GitHub Pages from the `main` branch's `docs/`
  folder at <https://manse404.github.io/pdf_assistant/demo/>. Its screenshots are `demo/razgovor.png`
  (a conversation with the "Under the hood" panel) and `demo/ocene.png` (the scores page). Moving or
  renaming `demo/` breaks the public link.
- `.nojekyll`: tells GitHub Pages to serve the folder as it is.

# pdf_assistant documentation

pdf_assistant is a conversation with one PDF: answers cite the page they come from, and every
conversation is also a small experiment that users' votes steer. The top-level
[README](../README.md) says how to run it in five minutes. These pages say how it works.

**Status: frozen as a demo since 2026-11-10; no work planned** ([ADR 0002](adr/0002-freeze-as-a-demo.md)).
Bug fixes are still welcome; there is no roadmap.

## Reading order

| # | Document | Read it when you want | Status | Last checked |
|---|---|---|---|---|
| 1 | [Vision](product/vision.md) | the problem it solves and how, why this way, for whom, what it is not, how it is measured, its status and what the demo shows | current | 2026-11-16 |
| 2 | [Feature catalogue](product/features/README.md) | every feature, what the user can do with it, its status and where it is in the code | current | 2026-11-16 |
| 3 | [Architecture overview](architecture/overview.md) | the one process, an upload and a question hop by hop, the experiment, accounts, data, tracing | current | 2026-11-16 |
| 4 | [Diagrams](diagrams/context.md) | the C4 [context](diagrams/context.md) and [container](diagrams/container.md) views | current | 2026-11-16 |
| 5 | [ADR 0001: rewrite on FastAPI without LangChain](adr/0001-rewrite-on-fastapi.md) | why the 2024 version was rewritten and what was kept | accepted | 2026-11-16 |
| 6 | [ADR 0002: freeze as a demo](adr/0002-freeze-as-a-demo.md) | why no new features are added here | accepted | 2026-11-16 |
| 7 | [Setup](guides/setup.md) | to run it locally, in Docker, through Ollama, with Supabase or Pinecone | current | 2026-11-16 |
| 8 | [Development](guides/development.md) | the checks, the tests and the live end-to-end script (which cannot pass as written) | current | 2026-11-16 |
| 9 | [Backend service](reference/services/backend.md) | what the FastAPI process does, how to run it, its start-up, settings and contracts | current | 2026-11-16 |
| 10 | [Client](reference/services/client.md) | the pages, the commands, the one setting and the contracts of the web client | current | 2026-11-16 |
| 11 | [Configuration](reference/configuration.md) | every setting with its default | current | 2026-11-16 |
| 12 | [HTTP API](reference/api.md) | every route and the answer stream | current | 2026-11-16 |
| 13 | [Codebase](reference/codebase.md) | the map of every tracked folder and the dependencies | current | 2026-11-16 |

## Other files here

- `demo/`: the static interactive demo, one self-contained `demo/index.html` that works when opened
  from a clone. It is meant to be published with GitHub Pages from the `main` branch's `docs/`
  folder at <https://manse404.github.io/pdf_assistant/demo/>; Pages is not turned on for the
  repository, so that address answers 404 for now. Its screenshots are `demo/razgovor.png` (a
  conversation with the "Under the hood" panel) and `demo/ocene.png` (the scores page). Moving or
  renaming `demo/` would break the published address once Pages is on.
- `.nojekyll`: tells GitHub Pages to serve the folder as it is.

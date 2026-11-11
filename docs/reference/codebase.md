# Codebase

A map of the repository. How the parts work together is in the
[architecture overview](../architecture/overview.md).

```
backend/
  src/pdf_assistant/
    api/
      main.py         create_app(): lifespan wiring, /api/health, upload size check, no-store
                      header, serving the built client at /
      auth.py         sign-up, sign-in, sign-out, current user
      pdfs.py         list, upload, show, download, delete PDFs
      conversations.py  conversations, the answer stream, votes, scores
      deps.py         Services (everything the routes use), current user
      schemas.py      response models
    ai/
      base.py         interfaces (ChatModel, Embedder), providers, errors
      openai_models.py  OpenAI, Azure OpenAI / Foundry and Ollama through the OpenAI API
      claude_models.py  Claude through the Anthropic SDK (API or Foundry): effort, fallback
      factory.py      builds the models and the embedder from the settings
    documents/
      storage.py      PDF files on disk or in Supabase Storage
      text.py         page text with pypdfium2, chunks that remember their page
      indexing.py     the indexing queue: file → chunks → embeddings → vector store
      service.py      PDF rows, scoped to their owner
    chat/
      components.py   the experiment: components, weights, the draw
      rag.py          follow-up rewrite, retrieval, prompt budget, cited sources
      service.py      conversation, message and vote rows, tallies
    vectors/
      base.py         the VectorStore interface, Chunk, Hit
      qdrant.py       Qdrant, embedded or a server; one collection filtered by PDF
      pinecone.py     Pinecone; one namespace per PDF
      factory.py      builds the store from the settings
    auth.py           bcrypt passwords and the JWT session cookie
    db.py             engine, sessions, UTC timestamps
    models.py         tables: users, pdfs, conversations, messages, votes
    tracing.py        Langfuse, off without keys
    settings.py       every setting
  alembic/            migrations: 0001 initial schema, 0002 closes the tables to the Supabase Data API
  tests/              pytest; helpers.py has scripted models, a keyword embedder and PDFs built in the test
  bin/
    init.sh           create or upgrade the database (alembic upgrade head)
    api.sh            the API with reload on 127.0.0.1:8000 (PORT to change)
    test.sh           pytest, arguments passed through
    check.sh          ruff check, ruff format --check, mypy, pytest
    e2e_live.sh       the Docker stack against real providers: one PDF, two questions, citations
  pyproject.toml      dependencies, ruff, mypy and pytest settings
client/               SvelteKit SPA (Svelte 5, Tailwind 4, pdf.js, chart.js, marked, DOMPurify)
  src/routes/         auth/signin, auth/signup, documents (list), documents/new (upload),
                      documents/[id] (PDF and chat), scores
  src/lib/api/        HTTP client, NDJSON stream reader, upload with progress, error messages
  src/lib/components/ shared components; chat/ (messages, sources, citations), pdf/ (viewer)
  src/lib/state/      auth, documents, chat and alert state
  src/lib/markdown/   rendering answers with citations
supabase/config.toml  local Supabase: database, Storage (private bucket pdfs), API, Studio
docs/demo/            the static interactive demo, published with GitHub Pages
Dockerfile            one image: the built client and the API
docker-compose.yml    the image on 127.0.0.1:8000 with a data volume and settings from .env
```

`client/build/` is listed in `.gitignore`, but three files under it (`index.html`, `favicon.png`,
`_app/version.json`) are tracked.

## Dependencies

| Where | Packages |
|---|---|
| Backend | FastAPI, uvicorn, pydantic-settings, python-multipart, SQLAlchemy 2.1, Alembic, bcrypt, PyJWT, `openai`, `anthropic`, `qdrant-client`, `pinecone`, pypdfium2, Langfuse, `storage3` (Supabase Storage), psycopg 3 (`backend/pyproject.toml`) |
| Backend, development | pytest, httpx, ruff, mypy |
| Client | `chart.js`, `dompurify`, `marked`, `pdfjs-dist`; SvelteKit with `adapter-static`, Vite, Tailwind with typography, TypeScript, ESLint, Prettier, Vitest (`client/package.json`) |

Python 3.14. Node 24 (`client/.nvmrc`); `engines` in `client/package.json` allows 22.17+, 24 and 26+.

# Codebase

A map of every tracked folder and file group. How the parts work together is in the
[architecture overview](../architecture/overview.md); the two parts that run are described in
[backend](services/backend.md) and [client](services/client.md).

## Shape

Two parts in one repository, each with its own manifest and lockfile: `backend/` (Python, uv) and
`client/` (Node, npm). In development they run as two processes (uvicorn and Vite); the Docker image
holds both, with the backend serving the built client. The backend keeps its routes in one `api/` package and its logic in packages by
capability (`documents/`, `chat/`, `ai/`, `vectors/`), with the shared pieces (settings, database,
tables, accounts, tracing) as single modules beside them.

## Map

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
    ai/               a copy of document-buddy's model layer without OCR (see ai/__init__.py)
      base.py         interfaces (ChatModel, Embedder), providers, errors, key redaction
      openai_models.py  OpenAI, Azure OpenAI / Foundry and Ollama through the OpenAI API
      claude_models.py  Claude through the Anthropic SDK (API or Foundry): effort, fallback
      factory.py      builds the models and the embedder from the settings
    documents/
      storage.py      PDF files on disk or in Supabase Storage
      text.py         page text with pypdfium2, chunks that never cross a page
      indexing.py     the indexing queue: file → chunks → embeddings → vector store
      service.py      PDF rows, scoped to their owner
    chat/
      components.py   the experiment: components, weights, the draw
      rag.py          follow-up rewrite, prompt budget, cited sources
      service.py      conversation, message and vote rows, tallies
    vectors/
      base.py         the VectorStore interface, Chunk, Hit
      qdrant.py       Qdrant, embedded or a server; one collection filtered by PDF
      pinecone.py     Pinecone; one namespace per PDF
      factory.py      builds the store from the settings
    auth.py           bcrypt passwords and the JWT session token
    db.py             engine, sessions, UTC timestamps
    models.py         tables: users, pdfs, conversations, messages, votes
    tracing.py        Langfuse, off without keys
    settings.py       every setting
  alembic/            migrations: 0001 initial schema, 0002 closes the tables to the Supabase Data API
  alembic.ini         Alembic configuration; the database URL comes from the settings
  tests/              pytest; helpers.py has scripted models, a keyword embedder, a recording tracer
                      and PDFs built in the test; conftest.py builds the app with them
  bin/
    init.sh           create or upgrade the database (alembic upgrade head)
    api.sh            the API with reload on 127.0.0.1:8000 (PORT to change)
    test.sh           pytest, arguments passed through
    check.sh          ruff check, ruff format --check, mypy, pytest
    e2e_live.sh       the Docker stack against real providers: one PDF, two questions, citations
  pyproject.toml      dependencies, ruff, mypy and pytest settings
  uv.lock             the locked dependencies
client/               SvelteKit SPA (Svelte 5, Tailwind 4, pdf.js, chart.js, marked, DOMPurify)
  src/routes/         auth/signin, auth/signup, documents (list), documents/new (upload),
                      documents/[id] (PDF and chat), scores; +layout.ts (sign-in guard),
                      +page.ts (/ → /documents), +error.svelte
  src/lib/api/        HTTP client, NDJSON stream reader, upload with progress, error messages,
                      the backend's response types
  src/lib/components/ shared components; chat/ (messages, sources, citations), pdf/ (viewer)
  src/lib/state/      auth, documents, chat and alert state (runes classes)
  src/lib/markdown/   rendering answers with citations
  src/lib/format.ts   Serbian formatting of dates, sizes and shares
  src/hooks.client.ts wires 401 to the sign-in page and server errors to alerts
  src/app.html, app.css, app.d.ts  page shell, Tailwind entry, SvelteKit types
  static/             favicon.png
  build/              three tracked files of a build output (see below)
  package.json, package-lock.json  dependencies and the npm scripts
  vite.config.ts      SvelteKit, Tailwind, the static adapter, the /api proxy, Vitest
  eslint.config.js, .prettierrc, .prettierignore, tsconfig.json  lint, format and type settings
  .nvmrc, .npmrc      Node 24; engine-strict
supabase/
  config.toml         local Supabase: database, Storage (private bucket pdfs), API, Studio
docs/                 this documentation; demo/ is the static interactive demo, .nojekyll is for
                      GitHub Pages
Dockerfile            one image: the built client and the API
docker-compose.yml    the image on 127.0.0.1:8000 with a data volume and settings from .env
.dockerignore, .gitignore  what stays out of the image and out of git
```

`client/build/` is listed in `.gitignore`, but three files under it (`index.html`, `favicon.png`,
`_app/version.json`) are tracked, and `npm run build` rewrites two of them. Nothing reads them from
git: the Dockerfile builds the client itself.

## Dependencies

| Where | Packages |
|---|---|
| Backend | FastAPI, uvicorn, pydantic-settings, python-multipart, SQLAlchemy 2.1, Alembic, bcrypt, PyJWT, `openai`, `anthropic`, `qdrant-client`, `pinecone`, pypdfium2, Langfuse, `storage3` (Supabase Storage), psycopg 3 (`backend/pyproject.toml`). The code also imports `httpx` and `httpx2` directly; they arrive through these packages and are not declared themselves. |
| Backend, development | pytest, httpx, ruff, mypy |
| Client | `chart.js`, `dompurify`, `marked`, `pdfjs-dist`; SvelteKit with `adapter-static`, Vite, Tailwind with typography, TypeScript, ESLint, Prettier, Vitest (`client/package.json`) |

Python 3.14. Node 24 (`client/.nvmrc`); `engines` in `client/package.json` allows 22.17+, 24 and 26+.

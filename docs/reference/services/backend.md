# Backend service

The FastAPI process in `backend/`: accounts, PDFs, indexing, conversations, votes and scores under
`/api`, and, when the client has been built, the client's files at `/`. In the Docker image it is
the only process; in development the [client](client.md) runs beside it under Vite.

## What it does

- Serves the HTTP API under `/api` ([HTTP API](../api.md)), OpenAPI at `/api/docs` and
  `/api/openapi.json`.
- Indexes uploaded PDFs in a thread pool inside the same process (`documents/indexing.py`):
  pypdfium2 text, page-aware chunks, embeddings, the vector store.
- Answers questions as a newline-delimited JSON stream (`api/conversations.py`, `chat/rag.py`).
- Serves the built client from `CLIENT_DIR` with an `index.html` fallback for every path outside
  `/api` (`api/main.py`, `_serve_client`).

Paths below are relative to `backend/src/pdf_assistant/` unless they start with `backend/`.

## How to run it

| Way | Command | What it does |
|---|---|---|
| Database | `backend/bin/init.sh` | `alembic upgrade head`; creates SQLite in `backend/data/` by default. Run it before the first start and after a pull with new migrations. |
| Development | `backend/bin/api.sh` | uvicorn with reload on `127.0.0.1:8000` (`PORT` to change), watching `src/` |
| Directly | `uv run uvicorn pdf_assistant.api.main:create_app --factory` | the app factory, in `backend/` |
| Docker | `docker compose up --build` | one image with the built client; runs `alembic upgrade head`, then uvicorn on port 8000 as a non-root user, data in the `/data` volume (`Dockerfile`) |

Requirements: [uv](https://docs.astral.sh/uv/) with Python 3.14 (`backend/pyproject.toml`,
`backend/uv.lock`). Checks: `backend/bin/check.sh` ([development guide](../../guides/development.md)).

## Start and stop

`create_app()` (`api/main.py`) builds everything in its lifespan from the settings, unless a test
passes its own: the database session factory, the tracer, the vector store, the embedder, the PDF
storage, the chat models, the experiment and the indexing queue. A missing key or an impossible
combination (Claude for embeddings, `PDF_STORAGE=supabase` without its URL and key,
`VECTOR_STORE=pinecone` without its key) stops the start with the name of the variable to set. PDFs
left `processing` by the previous run are queued again. On shutdown the queue cancels PDFs that have
not started (`documents/indexing.py`, `IndexQueue.shutdown`); they stay `processing` and are queued
again at the next start.

## Configuration

Environment variables or `backend/.env`, read once by `Settings` (`settings.py`); every variable
with its default is in the [configuration reference](../configuration.md). There is no
`.env.example`. The defaults need no service: SQLite, PDFs and embedded Qdrant under `DATA_DIR`
(`backend/data/`, git-ignored). Outside `ENVIRONMENT=dev` the app refuses to start with the
development `SECRET_KEY`.

## Contracts

| Contract | Defined in | Notes |
|---|---|---|
| HTTP API and answer stream | `api/*.py`, response models in `api/schemas.py` | [HTTP API](../api.md). The client's copy of these shapes is `client/src/lib/api/types.ts`, kept in step by hand. |
| Session cookie | `auth.py`, `api/auth.py` | `pdfa_session`: an HS256 JWT with `sub` and `exp`, httpOnly, path `/api`, `SameSite=Lax`, `Secure` outside `dev` |
| Database schema | `models.py`, `backend/alembic/versions/` | `0001` the tables, `0002` closes them to the Supabase Data API; `test_infrastructure.py` checks that the migrations build exactly the models |
| PDF files | `documents/storage.py` | one object `<id>.pdf` per PDF, in `DATA_DIR/pdfs` or the Supabase bucket |
| Vectors | `vectors/qdrant.py`, `vectors/pinecone.py` | Qdrant: one collection, point id `uuid5(pdf_id:chunk)`, payload `pdf_id`, `chunk`, `page`, `text`. Pinecone: one index, a namespace per PDF, record id = chunk number, metadata `chunk`, `page`, `text`. The vector size is fixed by the first embedding; a different size is refused. |
| Model providers | `ai/base.py` | `ChatModel` (`stream`, `complete`) and `Embedder` (`embed_documents`, `embed_query`); every provider error becomes `AiError` with key-like strings removed |
| Traces | `tracing.py` | Langfuse traces `chat-turn` (children `rewrite-followup`, `retrieve`, `answer`) and `index-pdf` (child `embed`); the user id is the Langfuse user, the conversation id the session |

## Outside systems

Model and embedding providers always (or Ollama on the same machine); optionally a Qdrant server or
Pinecone, Postgres (also Supabase's), Supabase Storage and Langfuse. Questions and passages go to the
configured model provider.

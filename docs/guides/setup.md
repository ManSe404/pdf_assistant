# Setup

How to run pdf_assistant locally, in Docker, without keys through Ollama, and with Supabase holding
the database and the PDFs. Every setting is in [the configuration reference](../reference/configuration.md).

## Requirements

- [uv](https://docs.astral.sh/uv/), which brings Python 3.14.
- Node 24 (or 22.17+; `client/.nvmrc` holds 24, so `nvm use` picks it). Node 25 cannot install the
  client's dependencies, because Vitest 5 does not support it.
- Docker, only for the image, local Supabase or the live end-to-end run.

By default no service has to run: SQLite and the Qdrant files live in `backend/data/`.

## Run locally

Model keys go in `backend/.env`:

```bash
ANTHROPIC_API_KEY=...     # answers (Claude)
OPENAI_API_KEY=...        # embeddings
```

```bash
backend/bin/init.sh                          # database (safe to run again)
backend/bin/api.sh                           # API on http://127.0.0.1:8000, docs at /api/docs
cd client && npm install && npm run dev      # client on http://127.0.0.1:5173
```

Vite proxies `/api` to `http://127.0.0.1:8000`; another port is set with
`API_URL=http://127.0.0.1:8010 npm run dev` (and `PORT=8010 backend/bin/api.sh`). The first account
is made on the sign-up page. When a key is missing, the API stops at start and the log names the
variable to set.

## Docker

```bash
docker compose up --build    # http://localhost:8000
```

One image holds the built client and the API. It brings the schema up to date (`alembic upgrade
head`) and then serves. Data lives in the volume `data`; settings are read from `.env` next to
`docker-compose.yml`. The port is published on `127.0.0.1` only.

## Without keys, through Ollama

```bash
CHAT_PROVIDER=ollama
CHAT_MODELS=llama3.2,gemma4:31b-cloud
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBED_DOCUMENT_PREFIX="search_document: "
EMBED_QUERY_PREFIX="search_query: "
```

From Docker, Ollama must listen on all addresses (`OLLAMA_HOST=0.0.0.0`), because the container calls
`host.docker.internal:11434`. Ollama is also the choice for documents that must not leave the
machine: with any other provider, questions and passages go to that provider.

## Supabase (local and cloud)

Supabase can hold the database (Postgres) and the PDFs (Storage), locally or as a project on
supabase.com. The code is the same; only addresses and keys change. Vectors still go to Qdrant or
Pinecone.

**Locally** (needs Docker). `supabase/config.toml` at the repository root starts only the database,
Storage, the API and Studio, and creates the private bucket `pdfs`:

```bash
npx supabase@2.122.1 start      # in the repository root
npx supabase@2.122.1 status     # addresses and keys
```

```bash
# backend/.env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
PDF_STORAGE=supabase
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SECRET_KEY=sb_secret_...    # "Secret" from supabase status
```

Then `backend/bin/init.sh` (migrations) and `backend/bin/api.sh`. Studio on
<http://127.0.0.1:54323> shows the tables and the uploaded PDFs. From a Docker container, use
`host.docker.internal` instead of `127.0.0.1`.

**Cloud** (a project on supabase.com):

```bash
DATABASE_URL=postgresql://postgres.<ref>:<password>@<session pooler>:5432/postgres
PDF_STORAGE=supabase
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...    # Project Settings → API Keys
```

- Copy `DATABASE_URL` from **Connect → Session pooler**:
  - the direct address `db.<ref>.supabase.co` works only over IPv6;
  - the transaction pooler (port 6543) does not support prepared statements, which psycopg uses.
- In the cloud the backend creates the bucket on the first upload: private, PDF only, up to
  `MAX_UPLOAD_MB`.

**Security.** Supabase exposes every table in the `public` schema through its REST and GraphQL API to
anyone with the public (publishable) key. Without protection, that key could read `users`, password
hashes included. Migration `0002` therefore turns on row level security without policies on Supabase
and revokes the `anon` and `authenticated` roles' grants; a request with the public key afterwards
gets `permission denied`. The backend connects as the tables' owner and is not restricted. On SQLite
and plain Postgres the migration does nothing.

## Pinecone

Every PDF gets its own namespace in one index, so a search needs no filter and deleting a PDF is one
call. For a local try there is [Pinecone Local](https://docs.pinecone.io/guides/operations/local-development).
It does not understand the new index-creation format, so the index is created with a REST call and
`PINECONE_HOST` gets the index address. The steps are in
`backend/tests/test_vectors.py::test_pinecone_local_round_trip`, which runs with
`PINECONE_LOCAL_HOST=http://localhost:5080`.

## Tracing

With `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` set, questions and indexing runs are traced in
Langfuse Cloud, or in a self-hosted Langfuse at `LANGFUSE_BASE_URL`. See
[the architecture overview](../architecture/overview.md#tracing).

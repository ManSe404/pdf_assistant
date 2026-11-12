# Development

The checks, the tests and the scripts. Running the app is in [setup](setup.md); the code map is in
[the codebase reference](../reference/codebase.md).

## Checks

```bash
backend/bin/check.sh       # ruff check, ruff format --check, mypy --strict, pytest
cd client && npm run check && npm run lint && npm test && npm run build
```

`backend/bin/check.sh` is what CI would run; there is no CI configured. Ruff uses line length 120
and the rule sets `E`, `F`, `W`, `I`, `B`, `UP`, `SIM`, `RUF`, `BLE`; mypy is strict with the pydantic
plugin over `src` (`backend/pyproject.toml`). On the client, `check` is `svelte-check`, `lint` is
Prettier and ESLint, `test` is Vitest over `src/**/*.test.ts`.

Other backend scripts: `backend/bin/test.sh` runs pytest with its arguments passed through
(`backend/bin/test.sh tests/test_api_chat.py -k vote`); `backend/bin/init.sh` creates or upgrades the
database; `backend/bin/api.sh` runs the API with reload.

## Backend tests

The backend tests never reach the network:

- models are scripted;
- the embedder works by keywords;
- Qdrant runs in memory;
- PDFs are built inside the test.

The provider tests run against a fake HTTP transport. `create_app()` takes its models, store, tracer
and storage as arguments, which is how the tests pass their own (`api/main.py`).

| File | Covers |
|---|---|
| `test_api_auth.py` | sign-up with an httpOnly cookie, sign-in and sign-out, wrong passwords, duplicates and bad passwords, forged or foreign cookies, closed sign-up |
| `test_api_pdfs.py` | upload and background indexing, the file served inline, non-PDF and oversized uploads, PDFs without text, embedding failures, file names, other users' PDFs, delete keeping votes, PDFs left `processing` indexed at the next start |
| `test_api_chat.py` | one component of each kind per conversation, the answer stream saved with its cited pages, the follow-up rewrite, the history limit, a failed answer, tracing of a turn, votes, scores, other users' conversations, experiments off, JSON 404 under `/api` |
| `test_text_and_rag.py` | page text, unreadable files, chunk size, overlap and boundaries, pages of chunks, the prompt budget, whole history turns, source numbering, the rewrite fallback |
| `test_components.py` | Serbian labels, satisfaction and weights, the weighted draw, components no longer configured |
| `test_ai_providers.py` | the OpenAI-compatible and Claude providers over a fake transport |
| `test_vectors.py` | Qdrant per PDF and deletion, embedding size checks, a Pinecone namespace per PDF; Pinecone Local when `PINECONE_LOCAL_HOST` is set |
| `test_storage.py` | save, read and delete on disk and Supabase, rejected uploads, Supabase bucket creation and errors, Postgres URLs, 503 while storage is down |
| `test_infrastructure.py` | migrations matching the models, Langfuse tracing and its failures, serving the built client, local defaults |

Storage has the same tests for disk and for Supabase. The Supabase part runs against a real stack when
these variables are set; each test creates and deletes its own bucket:

```bash
SUPABASE_TEST_URL=http://127.0.0.1:54321 SUPABASE_TEST_SECRET_KEY=sb_secret_... \
  uv run pytest tests/test_storage.py      # in backend/
```

## Client tests

Vitest covers the API error messages (`src/lib/api/errors.test.ts`), the NDJSON stream reader
(`src/lib/api/ndjson.test.ts`) and answer rendering with citations
(`src/lib/markdown/answer.test.ts`).

## Live end-to-end run

```bash
backend/bin/e2e_live.sh [report.json]
```

Starts the one-image stack with `docker compose up -d --build`, signs up a fresh user, uploads a
small PDF built by the script, waits for it to be ready, and asks two questions (the second a
follow-up). It exits 0 when the PDF is ready and both answers carry a citation. It refuses to start
without model keys in `.env` next to `docker-compose.yml`, so it never makes a fake run, and writes
its JSON report to `backend/data/e2e/` (git-ignored, like the rest of `backend/data/`) unless a path is given. `E2E_BASE_URL` points it at another
address.

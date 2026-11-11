# Configuration

Everything is set through environment variables or `backend/.env` (`backend/src/pdf_assistant/settings.py`).
Every default works for local development without any service running; only the model keys have to
be set, or the providers switched to Ollama. Empty values are ignored. Lists are comma-separated.
For Docker, the variables come from `.env` next to `docker-compose.yml`, which passes the settings
below into the container except the ones marked "not in compose" and the two the Dockerfile sets.

## Application and accounts

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev`, `staging` or `prod`. Outside `dev` a real `SECRET_KEY` is required and the cookie is `Secure`. |
| `SECRET_KEY` | a development value | Signs the session cookie. |
| `SESSION_DAYS` | `14` | How long a sign-in lasts. Not in compose. |
| `ALLOW_SIGNUP` | `true` | `false` closes sign-up. |
| `DATA_DIR` | `backend/data` | SQLite, uploaded PDFs, embedded Qdrant. Set to `/data` (a volume) by the Dockerfile. |
| `DATABASE_URL` | SQLite in `DATA_DIR` | A SQLAlchemy URL. A `postgresql://…` URL (for example from Supabase) works as it is; the driver is psycopg 3. |
| `MAX_UPLOAD_MB` | `50` | Not in compose. |
| `CLIENT_DIR` | `client/build` | The built web client served at `/`. Set to `/app/client` by the Dockerfile. |

## PDF storage

| Variable | Default | Notes |
|---|---|---|
| `PDF_STORAGE` | `disk` | `disk` (`DATA_DIR/pdfs`) or `supabase`. |
| `SUPABASE_URL` | none | For `PDF_STORAGE=supabase`; see [setup](../guides/setup.md#supabase-local-and-cloud). |
| `SUPABASE_SECRET_KEY` | none | A secret key (`sb_secret_…`) or a legacy `service_role` key; backend only. |
| `SUPABASE_BUCKET` | `pdfs` | Created private on the first upload when missing. |

## Models

| Variable | Default | Notes |
|---|---|---|
| `CHAT_PROVIDER` | `anthropic` | `anthropic`, `anthropic-foundry`, `openai`, `azure-openai`, `ollama`. |
| `CHAT_MODELS` | `claude-opus-5-5,claude-sonnet-5-5` | The models the experiment draws from. An entry can name its own provider: `openai:gpt-5.1`. On Azure, the model name is the deployment name. |
| `CLAUDE_EFFORT` | `low` | Claude only: `low` … `max`, or `default` to send none. |
| `EMBEDDING_PROVIDER` | `openai` | `openai`, `azure-openai` or `ollama`; Claude has no embeddings. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Changing it needs a new collection or index. |
| `EMBEDDING_DIMENSIONS` | none | Optional size passed to the embedding model. |
| `EMBED_DOCUMENT_PREFIX`, `EMBED_QUERY_PREFIX` | empty | Task prefixes some models want, for example `search_document: ` and `search_query: ` for `nomic-embed-text`. |
| `LLM_TIMEOUT_SECONDS` | `120` | Not in compose. |
| `ANTHROPIC_API_KEY` | none | Claude API. |
| `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_FOUNDRY_API_KEY` | none | Claude in Microsoft Foundry. |
| `OPENAI_API_KEY` | none | OpenAI. |
| `OPENAI_BASE_URL` | none | Any OpenAI-compatible server. |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` | none | Azure OpenAI / Microsoft Foundry. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | `http://host.docker.internal:11434` in compose. |

Provider combinations:

| Combination | Variables |
|---|---|
| Claude + OpenAI embeddings (default) | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |
| Everything in Microsoft Foundry | `CHAT_PROVIDER=anthropic-foundry`, `CHAT_MODELS=<Claude deployments>`, `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_FOUNDRY_API_KEY`; `EMBEDDING_PROVIDER=azure-openai`, `EMBEDDING_MODEL=<deployment>`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` |
| OpenAI only | `CHAT_PROVIDER=openai`, `CHAT_MODELS=<models>`, `OPENAI_API_KEY` |
| Mixed | `CHAT_MODELS=claude-opus-5-5,openai:gpt-5.1` with both keys |
| No keys, Ollama | see [setup](../guides/setup.md#without-keys-through-ollama) |

## Retrieval and the experiment

| Variable | Default | Notes |
|---|---|---|
| `RETRIEVER_TOP_K` | `3,5,8` | Passages per question; each at least 1. |
| `MEMORY_TURNS` | `0,2` | History per question; `0` is all the history that fits. |
| `EXPERIMENTS` | `true` | `false`: every conversation gets the first entry of each list. |
| `REWRITE_FOLLOWUPS` | `true` | A follow-up is rewritten into a standalone question before the search. Not in compose. |
| `MAX_PROMPT_TOKENS` | `24000` | The prompt budget. Not in compose. |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | `1000`, `150` | Characters; apply to new uploads; the overlap must be smaller than the size. Not in compose. |
| `EMBED_BATCH_SIZE` | `64` | Chunks per embedding call. Not in compose. |
| `INDEX_WORKERS` | `1` | Threads that index PDFs. Not in compose. |

## Vector store

| Variable | Default | Notes |
|---|---|---|
| `VECTOR_STORE` | `qdrant` | `qdrant` or `pinecone`. |
| `QDRANT_URL` | embedded in `DATA_DIR` | Embedded Qdrant holds its files locked, so it works with one process; for several uvicorn workers, point this at a Qdrant server. |
| `QDRANT_API_KEY` | none | |
| `QDRANT_COLLECTION` | `pdf_chunks` | |
| `PINECONE_API_KEY` | none | |
| `PINECONE_INDEX` | `pdf-assistant` | Created on first use (serverless) with the embedding size. |
| `PINECONE_HOST` | none | An index host, for example Pinecone Local. |
| `PINECONE_CLOUD`, `PINECONE_REGION` | `aws`, `us-east-1` | Where a new index is created. |

## Tracing

| Variable | Default | Notes |
|---|---|---|
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | none | Tracing is on when both are set. |
| `LANGFUSE_BASE_URL` | Langfuse Cloud (EU) | A self-hosted Langfuse. |

## Client

| Variable | Default | Notes |
|---|---|---|
| `API_URL` | `http://127.0.0.1:8000` | Where the Vite dev server (and `vite preview`) proxies `/api` (`client/vite.config.ts`). |

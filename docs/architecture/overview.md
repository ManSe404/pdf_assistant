# Architecture overview

How pdf_assistant is built: one process, what happens to an uploaded PDF and to a question, the
experiment, accounts and storage. The [context and container diagrams](../diagrams/context.md) show
the same parts as pictures; why it is built on FastAPI without LangChain is in
[ADR 0001](../adr/0001-rewrite-on-fastapi.md).

## Shape

One process serves everything: the API under `/api`, PDF indexing in a small thread pool, and the
built web client at `/` (`backend/src/pdf_assistant/api/main.py`). By default it needs no service at
all: SQLite, the uploaded PDFs and an embedded Qdrant live in `backend/data/`. Only the model keys
have to be set, or the providers switched to Ollama.

| Part | Choices | Code |
|---|---|---|
| Web client | SvelteKit single-page app (Svelte 5, Tailwind 4, pdf.js), built to `client/build` | `client/` |
| API | FastAPI, OpenAPI at `/api/docs` | `api/` |
| Database | SQLite (default) or Postgres, also Supabase's, through SQLAlchemy 2 and Alembic | `db.py`, `models.py`, `backend/alembic/` |
| PDF files | a folder on disk (default) or a private Supabase Storage bucket | `documents/storage.py` |
| Vectors | Qdrant, embedded on disk (default) or a server, or Pinecone | `vectors/` |
| Language models | Claude (Claude API or Microsoft Foundry), OpenAI, Azure OpenAI / Foundry, Ollama; each model in `CHAT_MODELS` may name its own provider | `ai/` |
| Embeddings | OpenAI, Azure OpenAI, Ollama (Claude has none) | `ai/` |
| Tracing | Langfuse, when both keys are set | `tracing.py` |

All choices are settings ([configuration](../reference/configuration.md)); the code is the same.

## An uploaded PDF

```
upload → PDF on disk or in Supabase Storage → text page by page (pypdfium2) → chunks with their page number
       → embeddings → vector store (Qdrant filtered by PDF, or a Pinecone namespace per PDF)
```

- **Upload** (`POST /api/pdfs`): up to `MAX_UPLOAD_MB` (50); a larger declared body is refused with
  413 before it is read. The file must be a PDF. The row is created as `processing` and the PDF is
  queued.
- **Indexing** (`documents/indexing.py`) runs in a thread pool of `INDEX_WORKERS` (1) inside the API
  process. Pages are read with pypdfium2; chunks of `CHUNK_SIZE` (1000) characters overlap by about
  `CHUNK_OVERLAP` (150), follow paragraphs, then lines, sentences and words, and remember the page
  they start on (`documents/text.py`). Chunks are embedded in batches of `EMBED_BATCH_SIZE` (64).
  The PDF ends `ready`, or `failed` with a message its owner sees.
- **A restart mid-run** leaves the PDF `processing`; at the next start every such PDF is queued
  again.
- **A scanned PDF** (no text layer) fails with an explanation: there is no OCR here.
- **Deleting a PDF** removes its rows (conversations and messages with it), its file and its vectors.

## A question

```
question → (a follow-up is rewritten into a standalone question)
         → embedding of the question → the k nearest chunks of this PDF
         → prompt with numbered chunks [1], [2] and their pages → the model streams the answer
         → the answer is saved with the sources it cites
```

- **Rewrite** (`REWRITE_FOLLOWUPS`, on by default): a follow-up such as "And the deposit?" is turned
  into a standalone search query with the conversation's recent messages, in the language of the
  question (`chat/rag.py`).
- **Prompt budget** (`MAX_PROMPT_TOKENS`, 24,000): the system text and the question always go in;
  then as many passages as fit, best first; then as much recent history as fits, whole
  question-answer pairs, newest first.
- **The model is told** to answer only from the numbered passages, cite them as `[n]`, say when the
  document does not answer, answer in the language of the question, and treat the passages as data,
  not instructions.
- **Streaming** (`POST /api/conversations/{id}/messages`): newline-delimited JSON events `start`,
  `delta` (repeated), then `end` with the saved answer and its sources, or `error` instead of `end`.
  An answer that breaks off is not saved, and a question without an answer is left out of the
  history.
- **Claude specifics** (`ai/claude_models.py`): thinking is left to the model and `CLAUDE_EFFORT`
  sets its depth (`low` by default; `default` sends none). On the Claude API, but not on Foundry,
  Opus 5.5, Opus 5, Fable 5.1 and Sonnet 5.5 get the server-side fallback: when a safety classifier
  declines a request, another model continues it.
- **Questions and passages leave the machine** for the configured model provider. Documents that must
  not leave it need Ollama.

## The experiment

Every conversation is also a small experiment: which language model, how many retrieved passages and
how much history work best, judged by the users' thumbs up and down (`chat/components.py`). When a
conversation starts, one component of each kind is drawn, weighted by votes:

| Kind | Set with | Default |
|---|---|---|
| language model | `CHAT_MODELS` | `claude-opus-5-5`, `claude-sonnet-5-5` |
| number of passages | `RETRIEVER_TOP_K` | 3, 5, 8 |
| history | `MEMORY_TURNS` (0 = all the history that fits) | all, the last 2 questions |

- **A component's weight** is `(up + 1) / (up + down + 1)`, at least 0.1. The "+1" is one imaginary
  thumbs up, so a component nobody voted on yet counts as fully satisfying and gets tried; the floor
  keeps a badly rated component from disappearing completely.
- **One vote per answer**, stored with the answer; it can be changed or withdrawn. Votes are counted
  across all users.
- **Votes are kept** when a conversation or a PDF is deleted.
- **The "Scores" page** (`GET /api/scores`) shows each component's votes, satisfaction and current
  weight, including components no longer configured.
- `EXPERIMENTS=false` turns it off: every conversation gets the first entry of each list.

## Accounts and access

- Sign-up and sign-in with e-mail and password (at least 8 characters, at most 72 bytes, the bcrypt
  limit); passwords are stored as bcrypt hashes (`auth.py`). `ALLOW_SIGNUP=false` closes sign-up.
- The session is a signed JWT (HS256, `SECRET_KEY`) in the httpOnly cookie `pdfa_session`, path
  `/api`, `SameSite=Lax`, valid `SESSION_DAYS` (14) days; `Secure` outside `dev`. Outside `dev` the
  app refuses to start with the development `SECRET_KEY`.
- Every PDF, conversation and message query is scoped to the signed-in user: a user sees only their
  own PDFs and conversations.
- API responses carry `Cache-Control: no-store`.
- On Supabase, migration `0002` turns on row level security without policies and revokes the `anon`
  and `authenticated` roles' grants, so Supabase's public Data API cannot read the tables (including
  password hashes) with the publishable key. The backend connects as the tables' owner and is not
  restricted. On SQLite and plain Postgres the migration does nothing.

## Data

Tables (`models.py`): `users` (e-mail, bcrypt hash), `pdfs` (owner, name, size, status, error,
pages, chunks, when indexed), `conversations` (PDF, owner, and the drawn `llm`, `retriever` and
`memory` components), `messages` (role, content, the sources an answer cites), `votes` (score, the
components it was given under, and the answer it belongs to, which becomes empty when the answer is
deleted, so the vote stays). Deleting a user, a PDF or a conversation deletes what belongs to it
below. Migrations in
`backend/alembic/versions/`: `0001` the initial schema, `0002` closing the tables to the Supabase Data
API. Uploaded files are one object per PDF, `<id>.pdf`, on disk under `DATA_DIR/pdfs` or in the bucket.

## Tracing

With `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` set, each question and each indexing run is one
Langfuse trace: the follow-up rewrite, the retrieval and the answer (with model and prompt), or the
embedding calls. The user is Langfuse's `user` and the conversation its `session`.
`LANGFUSE_BASE_URL` points at a self-hosted Langfuse; without it, Langfuse Cloud is used. A tracing
failure never fails a request.

## Constraints

- **Embedded Qdrant holds a file lock**, so it works with one process; more uvicorn workers need a
  Qdrant server (`QDRANT_URL`).
- **Changing the embedding model** needs a new Qdrant collection or Pinecone index.
- **No OCR**: scanned PDFs fail.
- **One PDF per conversation.**
- **The user interface and error messages are in Serbian.**

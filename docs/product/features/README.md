# Features

What pdf_assistant offers, read from its entry points: the HTTP routes in
`backend/src/pdf_assistant/api/`, the pages in `client/src/routes/`, the scripts in `backend/bin/`
and the static demo in `docs/demo/`. The project is [frozen as a demo](../../adr/0002-freeze-as-a-demo.md),
so nothing here is planned; the statuses say what exists. Backend paths are relative to
`backend/src/pdf_assistant/`.

| Feature | What you can do | Status | Where in code | Doc |
|---|---|---|---|---|
| Accounts | Sign up, sign in and sign out with e-mail and password; the owner of an instance can close sign-up | shipped | `api/auth.py`, `auth.py`; `client/src/routes/auth/` | [API](../../reference/api.md), [overview](../../architecture/overview.md#accounts-and-access) |
| Private library | See only your own PDFs, conversations and messages; another user's id answers "not found" | shipped | `documents/service.py`, `chat/service.py` | [overview](../../architecture/overview.md#accounts-and-access) |
| PDF upload | Pick a PDF of up to 50 MB, see the upload progress; non-PDFs and oversized files are refused | shipped | `api/pdfs.py`, `documents/storage.py`; `client/src/routes/documents/new/`, `client/src/lib/api/upload.ts` | [overview](../../architecture/overview.md#an-uploaded-pdf) |
| Background indexing | Watch a PDF go from processing to ready or failed with a reason; a restart picks up unfinished PDFs; a scanned PDF fails with an explanation | shipped | `documents/indexing.py`, `documents/text.py` | [overview](../../architecture/overview.md#an-uploaded-pdf) |
| Document list and delete | List your PDFs with status, size and date; delete one with its file, vectors and conversations | shipped | `api/pdfs.py`; `client/src/routes/documents/+page.svelte` | [API](../../reference/api.md) |
| PDF beside the conversation | Read the PDF next to the chat (tabs on a phone), select its text, follow a page counter; clicking a source scrolls to its page | shipped | `client/src/lib/components/pdf/PdfViewer.svelte`, `client/src/routes/documents/[id]/` | [client](../../reference/services/client.md) |
| Conversations | Keep several conversations per PDF: pick, start, delete; each is titled after its first question | shipped | `api/conversations.py`, `chat/service.py`; `client/src/lib/components/chat/ConversationBar.svelte` | [API](../../reference/api.md) |
| Cited answers | Ask a question and read a streamed Markdown answer that cites passages as `[n]` with their page, or says that the document does not say | shipped | `api/conversations.py`, `chat/rag.py`; `client/src/lib/state/chat.svelte.ts`, `client/src/lib/markdown/answer.ts` | [overview](../../architecture/overview.md#a-question) |
| Follow-up rewrite | Ask "And the deposit?" and have it searched as a standalone question | shipped | `chat/rag.py` (`standalone_question`) | [overview](../../architecture/overview.md#a-question) |
| Experiment draw | Each new conversation gets one model, passage count and history length, drawn with weights from earlier votes; can be turned off | shipped | `chat/components.py`, `chat/service.py` (`create_conversation`) | [overview](../../architecture/overview.md#the-experiment) |
| Votes | Give an answer a thumb up or down, change it or withdraw it | shipped | `api/conversations.py` (`vote`), `chat/service.py`; `client/src/lib/components/chat/AssistantMessage.svelte` | [API](../../reference/api.md) |
| Scores page | See each model, passage count and history length with its votes, satisfaction and current chance of being drawn | shipped | `api/conversations.py` (`scores`); `client/src/routes/scores/`, `client/src/lib/components/ScoreChart.svelte` | [overview](../../architecture/overview.md#the-experiment) |
| Model providers | Answer with Claude (Claude API or Microsoft Foundry), OpenAI, Azure OpenAI or Ollama, mixing providers in one experiment; embed with OpenAI, Azure OpenAI or Ollama | shipped | `ai/` | [configuration](../../reference/configuration.md#models) |
| Vector stores | Keep the vectors in embedded Qdrant, a Qdrant server or Pinecone | shipped | `vectors/` | [configuration](../../reference/configuration.md#vector-store) |
| Database and file storage | Keep the rows in SQLite or Postgres (also Supabase's) and the PDFs on disk or in a private Supabase Storage bucket, with the tables closed to Supabase's public Data API | shipped | `db.py`, `models.py`, `documents/storage.py`, `backend/alembic/versions/` | [setup](../../guides/setup.md#supabase-local-and-cloud) |
| Tracing | See each question and each indexing run as one Langfuse trace when the keys are set | shipped | `tracing.py` | [overview](../../architecture/overview.md#tracing) |
| One process, one image | Run the API, the indexing and the built client as one process, locally or as one Docker image that migrates on start | shipped | `api/main.py`, `Dockerfile`, `docker-compose.yml` | [backend](../../reference/services/backend.md), [setup](../../guides/setup.md#docker) |
| Live end-to-end script | Run the Docker image against real providers and check that both answers cite a page | broken | `backend/bin/e2e_live.sh` | [development](../../guides/development.md#live-end-to-end-run) |
| Interactive demo | Try the app in a browser without a server or keys, with invented documents and pre-written answers | partial | `docs/demo/index.html` | [vision](../vision.md#the-demo) |

## Accounts and the library

Accounts are e-mail and password with a bcrypt hash and a signed session cookie; every query for a
PDF, a conversation or a message is scoped to the signed-in user (`test_api_auth.py`,
`test_api_pdfs.py`, `test_api_chat.py`). An upload is checked twice: the client looks at the type,
the size and the `%PDF-` marker before sending, and the backend checks the marker and the size again
while it stores the file. The client's limit is fixed at 50 MB in `client/src/lib/api/upload.ts`;
the backend's follows `MAX_UPLOAD_MB`. Indexing runs in the API process; the list and the document
page poll every two seconds while a PDF is processing.

## Reading and asking

The document page puts the conversation and the PDF side by side from 1024 px up, and as two tabs
below that. pdf.js draws pages only when they scroll into view and adds a text layer, so text can be
selected. An answer streams as newline-delimited JSON, is rendered from Markdown with marked and
cleaned with DOMPurify, and turns each `[n]` into a button that opens the cited page. The prompt is
budgeted (`MAX_PROMPT_TOKENS`) and tells the model to answer only from the numbered passages. Covered
by `test_api_chat.py`, `test_text_and_rag.py` and the client's Vitest files.

## The experiment

A conversation is given one component of each kind when it starts, weighted by
`(up + 1) / (up + down + 1)` with a floor of 0.1, and keeps it. Votes are stored per answer and keep
counting when the conversation or the PDF is deleted. When `CHAT_MODELS`, `RETRIEVER_TOP_K` or
`MEMORY_TURNS` drop a component that a conversation was drawn with, that conversation is answered
with the first configured component, but its new votes still count for the dropped one
([architecture overview](../../architecture/overview.md#the-experiment)). Covered by
`test_components.py` and `test_api_chat.py`.

## Providers and storage

Every outside choice is a setting with the same code path. The offline tests check the Claude and
OpenAI-compatible providers against a fake HTTP transport (`test_ai_providers.py`), Qdrant in memory
and Pinecone against a fake client (`test_vectors.py`), and disk storage directly
(`test_storage.py`). The Supabase Storage tests and the Pinecone Local test run only when a real stack
is named in the environment ([development guide](../../guides/development.md#backend-tests)); none of
the tests reach a real model provider.

## Operations, the live check and the demo

`create_app()` serves the API under `/api`, OpenAPI at `/api/docs` and the built client at `/`; the
Docker image runs `alembic upgrade head` and then uvicorn. The live end-to-end script cannot pass as
written ([development guide](../../guides/development.md#live-end-to-end-run)). The demo is one
self-contained HTML file that works when opened from a clone; it is meant to be published with GitHub
Pages from the `main` branch's `docs/` folder, and Pages is not turned on for the repository, so its
public address answers 404.

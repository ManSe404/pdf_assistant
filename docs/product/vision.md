# Vision

pdf_assistant is a conversation with one PDF: a user uploads a PDF, asks questions, and every answer
cites the page it comes from. It is [frozen as a demo](#status).

## The problem or opportunity

**For someone with one long document.** People with a single long document, such as a contract or the
house rules of a building, want to know what it says about one thing, with the page to check the
answer against. The repository's own examples are of this kind: the demo (`docs/demo/index.html`) runs
over an invented lease for business premises and invented house rules, and the backend tests ask
"Koliki je rok za otkaz?" (what is the notice period?) and expect page 2 as the answer's source
(`backend/tests/test_api_chat.py`).

**For whoever runs such an app.** Which language model, how many retrieved passages and how much
conversation history give answers that people are satisfied with is not known in advance
(`backend/src/pdf_assistant/chat/components.py`).

**For someone who wants to see how it is built.** The opportunity is a demo: a small retrieval app
with citations, a pluggable model layer and an online experiment, built without a framework, that can
also be tried in the browser.

**The real case in this repository: the 2024 version.** The first version (Flask, Celery, Redis,
LangChain 0.0.352, OpenAI SDK 0.27, Pinecone 2), as [ADR 0001](../adr/0001-rewrite-on-fastapi.md)
records it:

- could not start, because `app/web/__init__.py` and `app/chat/__init__.py` were copies of other
  files;
- sent uploaded files to a course's upload service and traces to the course's Langfuse;
- needed three processes running, the server, the worker and Redis (its README, in the first commit);
- got its vote experiment wrong: a vote was not stored with its answer, so after a page reload the
  same answer could be voted on again, and a vote could be neither changed nor withdrawn.

Open: how people with such a document find answers today, how long it takes them and how often they
get it wrong is not recorded here. The repository has no user research and no usage data.

## How we solve it

The user uploads one PDF. The app reads its text page by page, cuts it into overlapping chunks that
each remember their page, and stores their embeddings. For a question it finds the chunks of that PDF
closest to the question and has a language model answer only from them, citing each passage as `[n]`.
When the passages do not hold the answer, the model is told to say that the document does not say.
The PDF sits beside the conversation, and clicking a source opens that page. A follow-up such as
"And the deposit?" is rewritten into a standalone question before the search.

Every conversation is also a small experiment. It is given, at random and weighted by earlier votes,
one language model, a number of passages to retrieve and an amount of history to send to the model.
Users rate answers with a thumb up or down, new conversations get better-rated combinations more
often, and the "Scores" page shows how each component is doing.

What changes afterwards:

- **The user** asks instead of reading through the document, and checks each answer on its cited page
  with one click.
- **Whoever runs it** lists candidates in `CHAT_MODELS`, `RETRIEVER_TOP_K` and `MEMORY_TURNS` instead
  of fixing one model and one retrieval setting up front, and lets the votes shift the draw
  (`EXPERIMENTS=false` turns this off).
- **A visitor** opens [the demo](#the-demo) in the browser, without a server or keys.

How each part works is in the [architecture overview](../architecture/overview.md).

## Why this way

Only one decision has an ADR. For the others, this section says what the repository records and
marks the rest open.

- **Fix the 2024 app instead of rewriting it.** Lost: it could not start, it depended on the course's
  services, and its vote experiment was wrong. Both halves were rewritten, keeping what made the app
  worth having: the experiment (now one vote per answer, stored in the database, changeable and
  withdrawable), the rewrite of follow-up questions and the PDF beside the conversation
  ([ADR 0001](../adr/0001-rewrite-on-fastapi.md)).
- **A server, a Celery worker and Redis as separate processes.** Replaced by one process: PDFs are
  indexed in a small thread pool inside the API process, and by default nothing but the model
  provider runs outside it (SQLite, files and embedded Qdrant under `backend/data/`)
  ([ADR 0001](../adr/0001-rewrite-on-fastapi.md), [architecture overview](../architecture/overview.md#shape)).
  The limit that comes with it: embedded Qdrant holds a file lock, so more than one process needs a
  Qdrant server.
- **LangChain for retrieval, prompts and streaming.** Dropped in the rewrite. The cost, recorded in
  ADR 0001: retrieval, prompt building and streaming are this repository's own code
  (`chat/rag.py`, `api/conversations.py`) and are maintained here. Open: ADR 0001 records the decision
  and its cost, not why a current LangChain was not chosen instead.
- **One fixed model provider, vector store, database and file storage.** Each is now a setting behind
  one small interface, with the same code path; tests replace each with a local stand-in
  ([ADR 0001](../adr/0001-rewrite-on-fastapi.md), [configuration](../reference/configuration.md)).
  Each model in `CHAT_MODELS` can name its own provider, so the experiment can compare models from
  different providers, and Ollama is the choice for documents that must not leave the machine.
- **One fixed model and retrieval setting, picked by hand.** Replaced by the experiment. The weight of
  a component is `(up + 1) / (up + down + 1)`, at least 0.1: the "+1" is one imaginary thumbs up, so a
  component nobody voted on yet gets tried, and the floor keeps a badly rated one from disappearing
  (`chat/components.py`). No ADR.
- **Grow this app with scans and OCR, folders, several documents and a shared knowledge base.** Not
  done here: these already exist in [document-buddy](https://github.com/ManSe404/document-buddy),
  which is moving to the Mosaic library, so pdf_assistant is frozen as a demo ([Status](#status)). No
  ADR.

## For whom

- **Users:** people who want answers from a single long document, such as a contract or house rules,
  with the page to check each answer against. The interface and error messages are in Serbian;
  answers come in the language of the question. Each user sees only their own PDFs and conversations.
- **Demo visitors:** anyone who wants to see a small retrieval app with citations, a pluggable model
  layer and an online experiment, built without a framework.
- **Whoever runs an instance** decides the model providers and their keys, whether sign-up is open
  (`ALLOW_SIGNUP`), whether the experiment runs (`EXPERIMENTS`) and where the database, the PDFs and
  the vectors live ([configuration](../reference/configuration.md)).
- **Who decides about the project:** the repository owner, who froze it and moved new features to
  document-buddy (`README.md`). Open: the repository names no other sponsor, client or user group.

## What it is not

- **Not for scanned PDFs.** There is no OCR; a PDF without a text layer fails with an explanation.
- **Not for several documents at once.** One PDF per conversation, no folders, no shared knowledge
  base; those are in document-buddy.
- **Not a general chatbot.** The model is told to answer only from the retrieved passages and to say
  when the document does not say.
- **Not private by default.** Questions and passages go to the configured model provider; documents
  that must not leave the machine need Ollama.
- **Not a shared workspace.** Users do not see each other's PDFs or conversations; only the votes are
  counted across all users.
- **Not a statistical test.** The "Scores" page shows each component's votes, satisfaction and current
  weight, with no confidence interval or significance test.
- **Not built to scale out as it is.** By default it is one process with embedded Qdrant; more uvicorn
  workers need a Qdrant server (`QDRANT_URL`).
- **Not growing.** Frozen as a demo: bug fixes only.

## How we know it works

That it works as built:

- `backend/bin/check.sh` runs ruff, mypy in strict mode and pytest. The backend tests never reach the
  network (the models are scripted and the embedder works by keywords), so they show the plumbing
  works: an answer saved with the pages it cites, the follow-up rewrite, votes and scores, one user's
  data out of another's reach. Which test covers what is in the
  [development guide](../guides/development.md#backend-tests).
- `cd client && npm run check && npm run lint && npm test && npm run build` checks the client.
- `backend/bin/e2e_live.sh` runs the Docker image against real model providers: one PDF, two
  questions (the second a follow-up). It exits 0 when the PDF is ready and both answers carry a
  citation, and refuses to start without model keys in `.env`.
- No CI is configured, so these run only when someone runs them.

That it solves the problem:

- Users' satisfaction with the answers is measured inside the app: the "Scores" page
  (`GET /api/scores`) shows the votes and satisfaction of each model, passage count and history.
- Open: whether a cited page really supports the answer is not measured. There is no evaluation set of
  questions with expected pages, and `e2e_live.sh` checks only that a citation exists.
- Open: whether users find answers faster or more reliably than by reading the document is not
  measured.

## Status

**Frozen as a demo.** The app works and the demo stays online, but no new features are added here.
Everything that would come next (scans and OCR, folders, several documents, a shared knowledge base)
already exists in [document-buddy](https://github.com/ManSe404/document-buddy), which is moving to the
Mosaic library. Bug fixes are still welcome.

## What it has

| Area | What exists |
|---|---|
| Accounts | Sign-up and sign-in (bcrypt, session in an httpOnly cookie), sign-out; sign-up is closed with `ALLOW_SIGNUP=false`. Every user sees only their own PDFs and conversations. |
| PDFs | Upload up to 50 MB (`MAX_UPLOAD_MB`) with a progress bar, a check that the file is a PDF, processing in the background with a status (processing / ready / error), processing resumed after a restart, delete (file, vectors, conversations). |
| Viewing | The PDF beside the conversation (pdf.js; pages are drawn only when they scroll into view), selectable text, a page counter; on a phone, Conversation and PDF tabs. |
| Conversation | Several conversations per PDF (pick, new, delete), a title from the first question, a streamed answer, Markdown, sources `[n]` that lead to the page, a list of passages, follow-ups rewritten (`REWRITE_FOLLOWUPS`), "the document does not say" when there is no answer. |
| Experiment | Model, passage count and history drawn per conversation, weighted by votes; a thumb up or down per answer (can be changed or withdrawn); the "Scores" page with satisfaction and the weight of each component; `EXPERIMENTS=false` turns it off. |
| Models | Claude (API or Microsoft Foundry), OpenAI, Azure OpenAI / Foundry, Ollama; each model in `CHAT_MODELS` can have its own provider. Embeddings: OpenAI, Azure, Ollama. |
| Search | Qdrant (embedded or a server) or Pinecone; chunks of 1000 characters with overlap, each remembering its page; a prompt budget (`MAX_PROMPT_TOKENS`). |
| Tracing | Langfuse traces for a question and for processing a PDF (user = user, conversation = session), when the keys exist. |
| Storage | Database: SQLite or Postgres. PDFs: disk or a private Supabase Storage bucket. Supabase works locally (`npx supabase start`) and in the cloud; the tables are closed to Supabase's public Data API. |
| Operations | One process (API + processing + built client), SQLite and files in `data/` by default, Alembic migrations, a Docker image, OpenAPI at `/api/docs`. |

How each works is in the [architecture overview](../architecture/overview.md).

## The demo

An [interactive demo](https://manse404.github.io/pdf_assistant/demo/) runs in the browser, without a
server or keys, over invented documents and with pre-written answers. It looks like the real app and
opens locally as `docs/demo/index.html`. In it you can:

- **ask about a contract** or house rules. The answer streams, and clicking `[1]` scrolls the PDF to that
  page and marks it;
- **ask a follow-up** ("And the deposit?"), which is rewritten into a standalone question before the
  search, and a question the document does not answer;
- **rate an answer** with a thumb, then see on the "Scores" page how satisfaction and the chance of
  each component change;
- **upload a sample PDF.** One goes through processing to "ready", and a scanned one ends as an error
  with an explanation;
- **open the "Under the hood" panel.** For every step it shows what the backend would do:
  - the draw of model, passage count and history, with the probabilities;
  - the rewrite of the follow-up;
  - the retrieved passages with their pages and similarity scores;
  - the prompt budget, the NDJSON stream and the Langfuse trace;
- **try the settings** in the panel's "Settings" tab: Claude, Foundry, OpenAI, Ollama or mixed;
  Qdrant or Pinecone; the experiment and tracing. It also simulates a model failing mid-answer. The
  tab prints the matching `.env`.

The demo's interface is in Serbian, like the app's.

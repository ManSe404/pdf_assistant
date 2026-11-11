# Vision

## What it is

A conversation with one PDF. A user uploads a PDF and asks questions; the answers cite the page they
come from. The PDF sits beside the conversation, and clicking a source opens that page.

It is also a small experiment. Every conversation is given, at random, one language model, a number of
passages to retrieve and an amount of history to send to the model. Users rate answers with a thumb up
or down, and new conversations get better-rated combinations more often. The "Scores" page shows how
each component is doing.

## For whom

People who want answers from a single long document, such as a contract or house rules, with the page
to check each answer against. And, as a demo, anyone who wants to see a small retrieval app with
citations, a pluggable model layer and an online experiment, built without a framework.

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

## Status

**Frozen as a demo.** The app works and the demo stays online, but no new features are added here.
Everything that would come next (scans and OCR, folders, several documents, a shared knowledge base)
already exists in [document-buddy](https://github.com/ManSe404/document-buddy), which is moving to the
Mosaic library. Bug fixes are still welcome.

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

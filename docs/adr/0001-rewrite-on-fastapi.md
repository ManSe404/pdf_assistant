# 0001. Rewrite on FastAPI without LangChain

## Status

Accepted (2026-11-05, commits "rewrite the backend on FastAPI and uv" and "rewrite the client on
Svelte 5 and SvelteKit 3").

## Context

The 2024 version:

- was Flask + Celery + Redis + LangChain 0.0.352 + OpenAI SDK 0.27 + Pinecone 2;
- sent uploaded files to the course's upload service and traces to the course's Langfuse;
- could not even start, because `app/web/__init__.py` and `app/chat/__init__.py` in the repository
  were copies of other files.

Its experiment with votes was also wrong:

- **Redis:** the API took a vote as a decimal number but wrote it with `HINCRBY`, which refuses
  decimals. The client sent only 1 and -1, so it did not break, but anything else would have.
- **The vote was not stored with the answer:** after a page reload the same answer could be voted on
  again, and a vote could be neither changed nor withdrawn.

## Decision

Rewrite both halves and keep what made the app worth having.

- Backend on FastAPI, SQLAlchemy 2 with Alembic, uv; no LangChain.
- Models of choice behind one small interface: Claude, OpenAI, Microsoft Foundry, Ollama.
- PDFs on disk or in Supabase Storage; the database SQLite or Postgres (Supabase, local or cloud).
- Qdrant or Pinecone behind one interface.
- Langfuse optional.
- A Svelte 5 client.
- Tests.

Kept from the old version: the experiment with votes, now corrected; the rewrite of follow-up
questions; the PDF shown beside the conversation. A vote is now one per answer, stored in the
database, and can be changed or withdrawn.

## Consequences

- Files and traces no longer go to the course's services. By default, apart from the model
  provider, nothing runs outside the one process (SQLite, files and embedded Qdrant under
  `backend/data/`).
- Each outside choice (model provider, vector store, PDF storage, database) is a setting, with the
  same code path; tests replace each with a local stand-in.
- Without LangChain, retrieval, prompt building and streaming are this repository's own code
  (`chat/rag.py`, `api/conversations.py`) and have to be maintained here.

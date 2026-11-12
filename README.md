# pdf_assistant

People with one long document, such as a contract or house rules, want answers from it that they can
check against the page they come from. pdf_assistant lets them upload the PDF and ask: answers come
only from the document's passages and cite their page, and clicking a source opens that page beside
the conversation. The problem, the approach and its limits are in the
[vision](docs/product/vision.md).

> **Status: frozen as a demo.** The app works and the demo stays online, but no new features are
> added here. Everything that would come next (scans and OCR, folders, several documents, a shared
> knowledge base) already exists in [document-buddy](https://github.com/ManSe404/document-buddy),
> which is moving to the Mosaic library. Bug fixes are still welcome.

The app is also a small experiment. Every conversation is given, at random, one language model, a
number of passages to retrieve and an amount of history to send to the model. Users rate answers with
a thumb up or down, and new conversations get better-rated combinations more often. The "Scores" page
shows how each component is doing.

FastAPI, SQLAlchemy and Alembic, Svelte 5; Claude, OpenAI, Microsoft Foundry or Ollama; Qdrant or
Pinecone; SQLite or Postgres (Supabase); optional Langfuse tracing. The interface is in Serbian.

## Demo

**[Open the interactive demo →](https://manse404.github.io/pdf_assistant/demo/)**

It runs in the browser, without a server or keys, over invented documents and with pre-written
answers. What it lets you try is in the [vision](docs/product/vision.md#the-demo).

[![A conversation with sources and the "Under the hood" panel](docs/demo/razgovor.png)](https://manse404.github.io/pdf_assistant/demo/?view=doc&state=done&hood=1)

[![Scores of the experiment's components](docs/demo/ocene.png)](https://manse404.github.io/pdf_assistant/demo/?view=scores&state=done)

## Run it in five minutes

You need [uv](https://docs.astral.sh/uv/) and Node 24 (or 22.17+). Model keys go in `backend/.env`:

```bash
ANTHROPIC_API_KEY=...     # answers (Claude)
OPENAI_API_KEY=...        # embeddings
```

```bash
backend/bin/init.sh                          # database (safe to run again)
backend/bin/api.sh                           # API on http://127.0.0.1:8000, docs at /api/docs
cd client && npm install && npm run dev      # client on http://127.0.0.1:5173
```

Or `docker compose up --build` for one image on <http://localhost:8000>, with settings from `.env`
next to `docker-compose.yml`. Without keys, through Ollama, with Supabase or Pinecone: see
[the setup guide](docs/guides/setup.md).

## Documentation

How it works, every setting, the API and the tests: [docs/README.md](docs/README.md).

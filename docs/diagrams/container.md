# Containers

What runs and where data lives, as in the Docker image: one process serves the API, the indexing
pool and the built client. In development the web client is served by Vite instead and forwards
`/api` to the API. The database and the PDF files sit inside the boundary in their default form
(SQLite and a folder in `DATA_DIR`); with Postgres or Supabase Storage they move outside it. Source:
[architecture overview](../architecture/overview.md), [backend](../reference/services/backend.md),
[client](../reference/services/client.md) and [codebase](../reference/codebase.md).

```mermaid
C4Container
  title pdf_assistant: containers

  Person(user, "User")

  System_Boundary(app, "pdf_assistant (one process, one Docker image)") {
    Container(client, "Web client", "SvelteKit SPA, Svelte 5, pdf.js", "Documents, PDF beside the chat, scores; built to client/build")
    Container(api, "API", "Python 3.14, FastAPI, uvicorn", "Auth, PDFs, conversations, answer stream, votes, scores; serves the client")
    Container(indexer, "Indexing pool", "Thread pool in the API process", "PDF text, chunks, embeddings into the vector store")
    ContainerDb(db, "Database", "SQLite in DATA_DIR, or Postgres", "users, pdfs, conversations, messages, votes")
    ContainerDb(files, "PDF files", "DATA_DIR/pdfs, or a Supabase Storage bucket", "One object per PDF")
    ContainerDb(qdrant, "Embedded Qdrant", "Files in DATA_DIR", "Chunks with page and PDF id; default vector store")
  }

  System_Ext(llm, "Model and embedding providers")
  System_Ext(ext_vectors, "Qdrant server or Pinecone")
  System_Ext(langfuse, "Langfuse")

  Rel(user, client, "Uses", "browser")
  Rel(client, api, "Calls", "JSON, multipart upload, NDJSON stream, session cookie")
  Rel(api, db, "Reads and writes")
  Rel(api, files, "Saves, reads, deletes")
  Rel(api, indexer, "Queues uploaded PDFs")
  Rel(indexer, files, "Reads")
  Rel(indexer, db, "Records status, pages and chunks")
  Rel(indexer, llm, "Embeds chunks")
  Rel(indexer, qdrant, "Stores chunks")
  Rel(indexer, ext_vectors, "Stores chunks, when configured")
  Rel(api, llm, "Rewrites follow-ups, embeds questions, streams answers")
  Rel(api, qdrant, "Searches; deletes a PDF's chunks")
  Rel(api, ext_vectors, "Searches and deletes, when configured")
  Rel(api, langfuse, "Traces, when keys are set")
  Rel(indexer, langfuse, "Traces, when keys are set")
```

# System context

pdf_assistant and the outside systems it can use. Every outside system except the model provider is
optional: by default the database, files and vectors stay inside the one process. Source:
[architecture overview](../architecture/overview.md#shape).

```mermaid
C4Context
  title pdf_assistant: system context

  Person(user, "User", "Uploads PDFs, asks questions, rates answers")

  System(app, "pdf_assistant", "Chat with one PDF; answers cite pages; votes steer the experiment")

  System_Ext(llm, "Model provider", "Claude API or Microsoft Foundry, OpenAI, Azure OpenAI, or Ollama")
  System_Ext(embed, "Embedding provider", "OpenAI, Azure OpenAI or Ollama")
  System_Ext(vectors, "Vector store server", "Qdrant server or Pinecone; optional, embedded Qdrant by default")
  System_Ext(supabase, "Supabase", "Postgres and Storage, local or cloud; optional")
  System_Ext(langfuse, "Langfuse", "Tracing; optional")

  Rel(user, app, "Uses", "browser")
  Rel(app, llm, "Questions and passages, streamed answers")
  Rel(app, embed, "Chunks and questions to embed")
  Rel(app, vectors, "Stores and searches chunks")
  Rel(app, supabase, "Rows and PDF files")
  Rel(app, langfuse, "Traces")
```

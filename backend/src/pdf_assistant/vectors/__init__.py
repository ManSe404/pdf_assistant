"""Where chunk vectors live: Qdrant (embedded on disk, or a server) or Pinecone."""

from pdf_assistant.vectors.base import Chunk, Hit, VectorStore, VectorStoreError

__all__ = ["Chunk", "Hit", "VectorStore", "VectorStoreError"]

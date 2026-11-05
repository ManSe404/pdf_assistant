"""Pinecone: one serverless index, one namespace per PDF.

A namespace per PDF means a search never needs a metadata filter and deleting a PDF is
one call. The index is created on first use with the embedding size.
"""

import threading
from collections.abc import Sequence
from typing import Any

from pinecone import Pinecone
from pinecone.errors import NotFoundError, PineconeError

from pdf_assistant.vectors.base import Chunk, Hit, VectorStoreError

_BATCH = 100
_TIMEOUT_SECONDS = 30.0


class PineconeStore:
    def __init__(
        self,
        client: Pinecone,
        *,
        index_name: str,
        index_host: str | None = None,
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        self._client = client
        self._index_name = index_name
        self._index_host = index_host
        self._cloud = cloud
        self._region = region
        self._index: Any = None  # pinecone.Index, created lazily
        self._lock = threading.Lock()

    def _get_index(self, size: int | None) -> Any:
        """The index; created (with ``size``) when missing and ``size`` is known."""
        with self._lock:
            if self._index is not None:
                return self._index
            try:
                if self._index_host:
                    self._index = self._client.index(host=self._index_host)
                    return self._index
                if not self._client.indexes.exists(self._index_name):
                    if size is None:
                        return None
                    self._client.indexes.create(
                        name=self._index_name,
                        schema={
                            "fields": {"embedding": {"type": "dense_vector", "dimension": size, "metric": "cosine"}}
                        },
                        deployment={"deployment_type": "managed", "cloud": self._cloud, "region": self._region},
                        timeout=300,
                    )
                else:
                    existing = self._client.indexes.describe(self._index_name).dimension
                    if size is not None and existing != size:
                        raise VectorStoreError(
                            f"Pinecone index '{self._index_name}' holds {existing}-dimension vectors but the "
                            f"embedding model returns {size}: set a new PINECONE_INDEX or re-upload the PDFs"
                        )
                self._index = self._client.index(self._index_name)
            except PineconeError as exc:
                raise VectorStoreError(f"Pinecone: {exc}") from exc
            return self._index

    def add(self, pdf_id: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk")
        if not chunks:
            return
        index = self._get_index(len(vectors[0]))
        records = [
            {
                "id": str(chunk.index),
                "values": list(vector),
                "metadata": {"chunk": chunk.index, "page": chunk.page, "text": chunk.text},
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            index.upsert(
                vectors=records, namespace=pdf_id, batch_size=_BATCH, show_progress=False, timeout=_TIMEOUT_SECONDS
            )
        except PineconeError as exc:
            raise VectorStoreError(f"Pinecone: {exc}") from exc

    def search(self, pdf_id: str, vector: Sequence[float], top_k: int) -> list[Hit]:
        index = self._get_index(None)
        if index is None:
            return []  # nothing indexed yet
        try:
            response = index.query(
                top_k=top_k, vector=list(vector), namespace=pdf_id, include_metadata=True, timeout=_TIMEOUT_SECONDS
            )
        except NotFoundError:
            return []
        except PineconeError as exc:
            raise VectorStoreError(f"Pinecone: {exc}") from exc
        hits = []
        for match in response.matches:
            metadata = match.metadata or {}
            hits.append(
                Hit(
                    index=int(metadata.get("chunk", 0)),
                    page=int(metadata.get("page", 1)),
                    text=str(metadata.get("text", "")),
                    score=float(match.score or 0.0),
                )
            )
        return hits

    def delete(self, pdf_id: str) -> None:
        index = self._get_index(None)
        if index is None:
            return
        try:
            # delete_all rather than delete_namespace: the same result on Pinecone, and
            # Pinecone Local accepts delete_namespace without deleting anything.
            index.delete(delete_all=True, namespace=pdf_id, timeout=_TIMEOUT_SECONDS)
        except NotFoundError:
            pass
        except PineconeError as exc:
            raise VectorStoreError(f"Pinecone: {exc}") from exc

    def close(self) -> None:
        pass

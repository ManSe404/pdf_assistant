"""Qdrant: embedded on disk by default (no server), or a Qdrant server via QDRANT_URL.

One collection holds every PDF; each point carries ``pdf_id`` and searches filter on it.
"""

import threading
import uuid
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from pdf_assistant.vectors.base import Chunk, Hit, VectorStoreError

_POINT_NAMESPACE = uuid.UUID("8f0b6f3e-2c1d-4c55-9a43-3c1b9e6a7d21")
_BATCH = 256


def point_id(pdf_id: str, index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{pdf_id}:{index}"))


def _pdf_filter(pdf_id: str) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="pdf_id", match=models.MatchValue(value=pdf_id))])


class QdrantStore:
    def __init__(self, client: QdrantClient, collection: str, *, embedded: bool) -> None:
        self._client = client
        self._collection = collection
        self._embedded = embedded
        # The embedded mode is not thread-safe; the indexing thread and request threads
        # share this client.
        self._lock = threading.Lock()
        self._ready_size: int | None = None

    def _ensure_collection(self, size: int) -> None:
        if self._ready_size == size:
            return
        if self._client.collection_exists(self._collection):
            params = self._client.get_collection(self._collection).config.params.vectors
            existing = params.size if isinstance(params, models.VectorParams) else None
            if existing != size:
                raise VectorStoreError(
                    f"Qdrant collection '{self._collection}' holds {existing}-dimension vectors but the "
                    f"embedding model returns {size}: set a new QDRANT_COLLECTION or re-upload the PDFs"
                )
        else:
            self._client.create_collection(
                self._collection, vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE)
            )
            if not self._embedded:  # payload indexes have no effect in embedded mode
                self._client.create_payload_index(
                    self._collection, "pdf_id", field_schema=models.PayloadSchemaType.KEYWORD
                )
        self._ready_size = size

    def add(self, pdf_id: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("one vector per chunk")
        if not chunks:
            return
        points = [
            models.PointStruct(
                id=point_id(pdf_id, chunk.index),
                vector=list(vector),
                payload={"pdf_id": pdf_id, "chunk": chunk.index, "page": chunk.page, "text": chunk.text},
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        with self._lock:
            self._ensure_collection(len(vectors[0]))
            for start in range(0, len(points), _BATCH):
                self._client.upsert(self._collection, points=points[start : start + _BATCH], wait=True)

    def search(self, pdf_id: str, vector: Sequence[float], top_k: int) -> list[Hit]:
        with self._lock:
            if not self._client.collection_exists(self._collection):
                return []
            result = self._client.query_points(
                self._collection,
                query=list(vector),
                query_filter=_pdf_filter(pdf_id),
                limit=top_k,
                with_payload=True,
            )
        hits = []
        for point in result.points:
            payload = point.payload or {}
            hits.append(
                Hit(
                    index=int(payload.get("chunk", 0)),
                    page=int(payload.get("page", 1)),
                    text=str(payload.get("text", "")),
                    score=point.score,
                )
            )
        return hits

    def delete(self, pdf_id: str) -> None:
        with self._lock:
            if not self._client.collection_exists(self._collection):
                return
            self._client.delete(
                self._collection, points_selector=models.FilterSelector(filter=_pdf_filter(pdf_id)), wait=True
            )

    def close(self) -> None:
        with self._lock:
            self._client.close()

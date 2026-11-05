import os
import uuid
from typing import Any

import pytest
from pinecone.errors import NotFoundError
from qdrant_client import QdrantClient

from pdf_assistant.vectors import Chunk, VectorStoreError
from pdf_assistant.vectors.pinecone import PineconeStore
from pdf_assistant.vectors.qdrant import QdrantStore

CHUNKS = [Chunk(0, 1, "prvi"), Chunk(1, 2, "drugi")]
VECTORS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


def test_qdrant_searches_one_pdf_and_deletes_it() -> None:
    store = QdrantStore(QdrantClient(":memory:"), "t", embedded=True)
    assert store.search("a", [1.0, 0.0, 0.0], 5) == []  # before the collection exists
    store.add("a", CHUNKS, VECTORS)
    store.add("b", [Chunk(0, 7, "tudji")], [[1.0, 0.0, 0.0]])

    hits = store.search("a", [0.9, 0.1, 0.0], 5)
    assert [(h.index, h.page, h.text) for h in hits] == [(0, 1, "prvi"), (1, 2, "drugi")]
    assert hits[0].score > hits[1].score

    store.add("a", CHUNKS, VECTORS)  # a re-run overwrites, it does not duplicate
    assert len(store.search("a", [1.0, 0.0, 0.0], 10)) == 2

    store.delete("a")
    assert store.search("a", [1.0, 0.0, 0.0], 5) == []
    assert [h.text for h in store.search("b", [1.0, 0.0, 0.0], 5)] == ["tudji"]
    store.delete("unknown")


def test_qdrant_refuses_a_different_embedding_size() -> None:
    client = QdrantClient(":memory:")
    QdrantStore(client, "t", embedded=True).add("a", CHUNKS, VECTORS)
    with pytest.raises(VectorStoreError, match="QDRANT_COLLECTION"):
        QdrantStore(client, "t", embedded=True).add("b", [Chunk(0, 1, "x")], [[1.0, 0.0]])


# ------------------------------------------------------------------ Pinecone, fake client


class _FakeIndex:
    def __init__(self) -> None:
        self.namespaces: dict[str, dict[str, dict[str, Any]]] = {}

    def upsert(self, *, vectors: list[dict[str, Any]], namespace: str, **_: Any) -> None:
        self.namespaces.setdefault(namespace, {}).update({v["id"]: v for v in vectors})

    def query(self, *, top_k: int, vector: list[float], namespace: str, include_metadata: bool, **_: Any) -> Any:
        if namespace not in self.namespaces:
            raise NotFoundError("namespace not found")

        class Match:
            def __init__(self, record: dict[str, Any]) -> None:
                self.id, self.metadata = record["id"], record["metadata"]
                self.score = sum(a * b for a, b in zip(record["values"], vector, strict=True))

        matches = sorted((Match(r) for r in self.namespaces[namespace].values()), key=lambda m: -m.score)
        return type("Response", (), {"matches": matches[:top_k]})()

    def delete(self, *, delete_all: bool, namespace: str, **_: Any) -> None:
        assert delete_all
        if namespace not in self.namespaces:
            raise NotFoundError("namespace not found")
        del self.namespaces[namespace]


class _FakeIndexes:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.dimension: int | None = None

    def exists(self, name: str) -> bool:
        return self.dimension is not None

    def create(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        self.dimension = kwargs["schema"]["fields"]["embedding"]["dimension"]

    def describe(self, name: str) -> Any:
        return type("Model", (), {"dimension": self.dimension})()


class _FakePinecone:
    def __init__(self) -> None:
        self.indexes = _FakeIndexes()
        self.the_index = _FakeIndex()

    def index(self, name: str = "", *, host: str = "") -> _FakeIndex:
        return self.the_index


def test_pinecone_uses_one_namespace_per_pdf_and_creates_the_index_once() -> None:
    client = _FakePinecone()
    store = PineconeStore(client, index_name="pdf-assistant")  # type: ignore[arg-type]
    assert store.search("a", [1.0, 0.0, 0.0], 3) == []  # no index yet, nothing created
    assert client.indexes.created == []

    store.add("a", CHUNKS, VECTORS)
    [created] = client.indexes.created
    assert created["schema"]["fields"]["embedding"] == {"type": "dense_vector", "dimension": 3, "metric": "cosine"}
    assert created["deployment"] == {"deployment_type": "managed", "cloud": "aws", "region": "us-east-1"}
    assert set(client.the_index.namespaces) == {"a"}

    hits = store.search("a", [1.0, 0.0, 0.0], 1)
    assert [(h.page, h.text) for h in hits] == [(1, "prvi")]
    assert store.search("never-indexed", [1.0, 0.0, 0.0], 3) == []

    store.delete("a")
    store.delete("a")  # already gone: fine
    assert client.the_index.namespaces == {}


def test_pinecone_refuses_a_different_embedding_size() -> None:
    client = _FakePinecone()
    client.indexes.dimension = 1536
    store = PineconeStore(client, index_name="pdf-assistant")  # type: ignore[arg-type]
    with pytest.raises(VectorStoreError, match="PINECONE_INDEX"):
        store.add("a", CHUNKS, VECTORS)


# ------------------------------------------------------------------ Pinecone Local (optional)


@pytest.mark.skipif(not os.environ.get("PINECONE_LOCAL_HOST"), reason="set PINECONE_LOCAL_HOST to run")
def test_pinecone_local_round_trip() -> None:
    """Against Pinecone Local (docker image ghcr.io/pinecone-io/pinecone-local), e.g.
    PINECONE_LOCAL_HOST=http://localhost:5080 uv run pytest -k pinecone_local

    Pinecone Local only understands the older index-creation body, so the index is made
    with a REST call and the store gets its host (PINECONE_HOST), as a user of Pinecone
    Local would set it up."""
    import httpx
    from pinecone import Pinecone

    control = os.environ["PINECONE_LOCAL_HOST"]
    name = f"test-{uuid.uuid4().hex[:8]}"
    created = httpx.post(
        f"{control}/indexes",
        headers={"Api-Key": "pclocal"},
        json={
            "name": name,
            "dimension": 3,
            "metric": "cosine",
            "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}},
        },
        timeout=30,
    )
    assert created.status_code == 201, created.text
    host = created.json()["host"]
    store = PineconeStore(Pinecone(api_key="pclocal", host=control), index_name=name, index_host=f"http://{host}")
    try:
        store.add("pdf-a", CHUNKS, VECTORS)
        hits = store.search("pdf-a", [1.0, 0.0, 0.0], 2)
        assert [h.text for h in hits] == ["prvi", "drugi"] and hits[0].page == 1
        assert store.search("pdf-b", [1.0, 0.0, 0.0], 2) == []
        store.delete("pdf-a")
        assert store.search("pdf-a", [1.0, 0.0, 0.0], 2) == []
        store.delete("pdf-a")
    finally:
        httpx.delete(f"{control}/indexes/{name}", headers={"Api-Key": "pclocal"}, timeout=30)

from qdrant_client import QdrantClient

from pdf_assistant.settings import Settings, VectorStoreKind
from pdf_assistant.vectors.base import VectorStore, VectorStoreError

_TIMEOUT_SECONDS = 30


def build_vector_store(settings: Settings) -> VectorStore:
    if settings.vector_store is VectorStoreKind.PINECONE:
        from pinecone import Pinecone

        from pdf_assistant.vectors.pinecone import PineconeStore

        if not settings.pinecone_api_key:
            raise VectorStoreError("PINECONE_API_KEY must be set to use VECTOR_STORE=pinecone")
        client = Pinecone(api_key=settings.pinecone_api_key.get_secret_value(), timeout=_TIMEOUT_SECONDS)
        return PineconeStore(
            client,
            index_name=settings.pinecone_index,
            index_host=settings.pinecone_host,
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
        )

    from pdf_assistant.vectors.qdrant import QdrantStore

    if settings.qdrant_url:
        api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
        remote = QdrantClient(url=settings.qdrant_url, api_key=api_key, timeout=_TIMEOUT_SECONDS)
        return QdrantStore(remote, settings.qdrant_collection, embedded=False)
    path = settings.data_dir / "qdrant"
    path.mkdir(parents=True, exist_ok=True)
    return QdrantStore(QdrantClient(path=str(path)), settings.qdrant_collection, embedded=True)

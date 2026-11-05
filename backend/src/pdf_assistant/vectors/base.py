"""The vector store interface. Every chunk belongs to one PDF and is only ever searched
within that PDF."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Chunk:
    index: int  # position in the PDF, 0-based
    page: int  # 1-based page the chunk starts on
    text: str


@dataclass(frozen=True)
class Hit:
    index: int
    page: int
    text: str
    score: float


class VectorStoreError(Exception):
    """The store is unreachable or set up for a different embedding size."""


class VectorStore(Protocol):
    def add(self, pdf_id: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        """Store the chunks of one PDF. Creates the collection or index on first use."""
        ...

    def search(self, pdf_id: str, vector: Sequence[float], top_k: int) -> list[Hit]:
        """The closest chunks of one PDF, best first."""
        ...

    def delete(self, pdf_id: str) -> None:
        """Remove every chunk of one PDF. Removing an unknown PDF is not an error."""
        ...

    def close(self) -> None: ...

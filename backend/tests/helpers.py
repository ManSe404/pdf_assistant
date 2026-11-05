"""Test doubles and builders: PDFs made in memory, a keyword embedder, scripted chat
models and a tracer that records what it was asked to trace."""

import hashlib
import math
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pdf_assistant.ai import AiError, ChatMessage

# ------------------------------------------------------------------ PDFs


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: Sequence[str]) -> bytes:
    """A valid PDF with one Helvetica text block per page (ASCII text; an empty string
    makes a page without text). Lines of each page become separate text lines."""
    objects: list[bytes] = []
    page_ids = [3 + 2 * i for i in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for pid, text in zip(page_ids, pages, strict=True):
        lines = [f"({_escape(line)}) Tj T*" for line in text.split("\n")] if text else []
        stream = ("BT /F1 11 Tf 14 TL 50 780 Td " + " ".join(lines) + " ET").encode() if lines else b""
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents {pid + 1} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# ------------------------------------------------------------------ models

_WORD = re.compile(r"[a-z0-9]+")


class KeywordEmbedder:
    """Bag of hashed words, normalized: texts sharing words are close. Deterministic and
    good enough to check that retrieval finds the passage that contains the answer."""

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions
        self.queries: list[str] = []
        self.documents: list[str] = []
        self.fail_documents = False

    @property
    def name(self) -> str:
        return "keyword-test-embedder"

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in _WORD.findall(text.lower()):
            if len(word) < 3:
                continue
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail_documents:
            raise AiError("model request failed (401): bad key")
        self.documents.extend(texts)
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self._vector(text)


@dataclass
class ScriptedChat:
    """Streams ``answer`` in pieces; ``complete`` (the follow-up rewrite) returns
    ``rewrite``. Records every call."""

    model: str
    answer: str = "Rok je 30 dana [1]."
    rewrite: str = "standalone question"
    fail_after: int | None = None  # raise AiError after this many pieces
    streams: list[dict[str, Any]] = field(default_factory=list)
    completions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.model

    async def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.streams.append({"system": system, "messages": list(messages)})
        pieces = re.findall(r"\S+\s*", self.answer)
        for i, piece in enumerate(pieces):
            if self.fail_after is not None and i >= self.fail_after:
                raise AiError("Claude request failed: connection dropped")
            yield piece

    async def complete(self, *, system: str, messages: Sequence[ChatMessage]) -> str:
        self.completions.append({"system": system, "messages": list(messages)})
        return self.rewrite


# ------------------------------------------------------------------ tracing


@dataclass
class RecordedObservation:
    name: str
    kind: str
    input: Any = None
    model: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list[RecordedObservation] = field(default_factory=list)
    ends: list[dict[str, Any]] = field(default_factory=list)

    def child(
        self,
        name: str,
        *,
        as_type: str = "span",
        input: Any = None,
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RecordedObservation:
        observation = RecordedObservation(name, as_type, input, model, dict(metadata or {}))
        self.children.append(observation)
        return observation

    def end(self, *, output: Any = None, error: str | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        self.ends.append({"output": output, "error": error})


class RecordingTracer:
    def __init__(self) -> None:
        self.traces: list[RecordedObservation] = []

    def start(
        self,
        name: str,
        *,
        user_id: str,
        session_id: str | None = None,
        input: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> RecordedObservation:
        root = RecordedObservation(
            name, "chain", input, attributes={"user_id": user_id, "session_id": session_id, **(metadata or {})}
        )
        self.traces.append(root)
        return root

    def shutdown(self) -> None:
        pass

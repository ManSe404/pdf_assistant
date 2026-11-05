"""Indexing: PDF file -> page text -> chunks -> embeddings -> vector store.

Runs in a small thread pool inside the API process. A PDF is ``processing`` until the
run ends as ``ready`` or ``failed`` (with a message the owner sees). PDFs still
``processing`` when the process starts (it stopped mid-run) are queued again.
"""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pdf_assistant.ai import AiError, Embedder
from pdf_assistant.db import session_scope, utcnow
from pdf_assistant.documents.storage import PdfFileMissing, PdfStorage, StorageError
from pdf_assistant.documents.text import PdfUnreadable, chunk_pages, read_pages
from pdf_assistant.models import Pdf, PdfStatus
from pdf_assistant.tracing import Tracer
from pdf_assistant.vectors import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)

NO_TEXT = (
    "PDF nema tekstualni sloj (verovatno je skeniran), pa nema šta da se pretražuje. "
    "Skenirani PDF-ovi se ovde ne čitaju OCR-om."
)


class Indexer:
    def __init__(
        self,
        *,
        sessions: sessionmaker[Session],
        storage: PdfStorage,
        embedder: Embedder,
        store: VectorStore,
        tracer: Tracer,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
    ) -> None:
        self._sessions = sessions
        self._storage = storage
        self._embedder = embedder
        self._store = store
        self._tracer = tracer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._batch_size = batch_size

    def index(self, pdf_id: str) -> None:
        with session_scope(self._sessions) as db:
            pdf = db.get(Pdf, pdf_id)
            if pdf is None:
                return
            user_id, name = pdf.user_id, pdf.name
        trace = self._tracer.start("index-pdf", user_id=user_id, input={"pdf_id": pdf_id, "name": name})
        try:
            pages = read_pages(self._storage.read(pdf_id))
            chunks = chunk_pages(pages, size=self._chunk_size, overlap=self._chunk_overlap)
            if not chunks:
                raise PdfUnreadable(NO_TEXT)
            self._store.delete(pdf_id)  # a re-run replaces, never duplicates
            embed = trace.child(
                "embed", as_type="embedding", model=self._embedder.name, metadata={"chunks": len(chunks)}
            )
            try:
                for start in range(0, len(chunks), self._batch_size):
                    batch = chunks[start : start + self._batch_size]
                    vectors = self._embedder.embed_documents([c.text for c in batch])
                    self._store.add(pdf_id, batch, vectors)
            except Exception as exc:
                embed.end(error=str(exc))
                raise
            embed.end(output={"chunks": len(chunks)})
        except PdfUnreadable as exc:
            self._finish(pdf_id, error=str(exc))
            trace.end(error=str(exc))
            return
        except AiError as exc:
            self._finish(pdf_id, error=f"Model za embedding nije uspeo: {exc}")
            trace.end(error=str(exc))
            return
        except VectorStoreError as exc:
            self._finish(pdf_id, error=f"Baza vektora nije uspela: {exc}")
            trace.end(error=str(exc))
            return
        except PdfFileMissing:
            self._finish(pdf_id, error="Fajl ovog PDF-a više ne postoji u skladištu; otpremi ga ponovo.")
            trace.end(error="file missing")
            return
        except StorageError as exc:
            self._finish(pdf_id, error=f"Skladište PDF-ova nije uspelo: {exc}")
            trace.end(error=str(exc))
            return
        except Exception as exc:
            logger.exception("indexing %s failed", pdf_id)
            self._finish(pdf_id, error="Obrada nije uspela zbog neočekivane greške; pogledaj log servera.")
            trace.end(error=repr(exc))
            return
        if not self._finish(pdf_id, pages=len(pages), chunks=len(chunks)):
            # Deleted while it was being indexed: drop what was just stored.
            self._store.delete(pdf_id)
        trace.end(output={"pages": len(pages), "chunks": len(chunks)})

    def _finish(
        self, pdf_id: str, *, error: str | None = None, pages: int | None = None, chunks: int | None = None
    ) -> bool:
        """Record the result; False when the PDF no longer exists."""
        with session_scope(self._sessions) as db:
            pdf = db.get(Pdf, pdf_id)
            if pdf is None:
                return False
            pdf.status = PdfStatus.FAILED if error else PdfStatus.READY
            pdf.error = error
            if pages is not None:
                pdf.pages = pages
                pdf.chunks = chunks
            pdf.indexed_at = utcnow()
            return True


class IndexQueue:
    def __init__(self, indexer: Indexer, *, workers: int) -> None:
        self._indexer = indexer
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="index")
        self._pending: set[Future[None]] = set()
        self._lock = threading.Lock()

    def submit(self, pdf_id: str) -> Future[None]:
        future = self._pool.submit(self._run, pdf_id)
        with self._lock:
            self._pending.add(future)
        future.add_done_callback(self._forget)
        return future

    def _forget(self, future: Future[None]) -> None:
        with self._lock:
            self._pending.discard(future)

    def wait_idle(self, timeout: float = 30) -> bool:
        """Block until every queued PDF is done (tests, scripts). False on timeout."""
        with self._lock:
            pending = set(self._pending)
        _, not_done = wait(pending, timeout=timeout)
        return not not_done

    def _run(self, pdf_id: str) -> None:
        try:
            self._indexer.index(pdf_id)
        except Exception:
            logger.exception("indexing %s crashed", pdf_id)

    def resume(self, sessions: sessionmaker[Session]) -> int:
        """Queue the PDFs left ``processing`` by a previous run."""
        with session_scope(sessions) as db:
            pending = list(db.scalars(select(Pdf.id).where(Pdf.status == PdfStatus.PROCESSING)))
        for pdf_id in pending:
            self.submit(pdf_id)
        return len(pending)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

"""The FastAPI app: the API under /api and, when it has been built, the web client at /.

Run with ``uvicorn pdf_assistant.api.main:create_app --factory``. Tests pass their own
models, store and tracer so nothing reaches a real provider.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session, sessionmaker

from pdf_assistant.ai import ChatModel, Embedder
from pdf_assistant.ai.factory import build_chat_models, build_embedder, chat_model_refs
from pdf_assistant.api import auth, conversations, pdfs
from pdf_assistant.api.deps import Services
from pdf_assistant.chat.components import Experiment
from pdf_assistant.db import make_engine, make_session_factory
from pdf_assistant.documents.indexing import Indexer, IndexQueue
from pdf_assistant.documents.storage import PdfStorage, build_pdf_storage
from pdf_assistant.settings import Settings, get_settings
from pdf_assistant.tracing import Tracer, build_tracer
from pdf_assistant.vectors import VectorStore
from pdf_assistant.vectors.factory import build_vector_store

logger = logging.getLogger(__name__)
_MULTIPART_OVERHEAD = 64 * 1024  # boundaries and part headers around the file


def create_app(
    settings: Settings | None = None,
    *,
    sessions: sessionmaker[Session] | None = None,
    chat_models: dict[str, ChatModel] | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
    tracer: Tracer | None = None,
    storage: PdfStorage | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        session_factory = sessions or make_session_factory(make_engine(settings.sqlalchemy_url))
        services_tracer = tracer or build_tracer(settings)
        services_store = store or build_vector_store(settings)
        services_embedder = embedder or build_embedder(settings)
        pdf_storage = storage or build_pdf_storage(settings)
        indexer = Indexer(
            sessions=session_factory,
            storage=pdf_storage,
            embedder=services_embedder,
            store=services_store,
            tracer=services_tracer,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            batch_size=settings.embed_batch_size,
        )
        queue = IndexQueue(indexer, workers=settings.index_workers)
        app.state.services = Services(
            settings=settings,
            sessions=session_factory,
            storage=pdf_storage,
            chat_models=chat_models or build_chat_models(settings),
            embedder=services_embedder,
            store=services_store,
            tracer=services_tracer,
            experiment=Experiment(
                models=chat_model_refs(settings),
                top_ks=settings.retriever_top_k,
                memory_turns=settings.memory_turns,
                enabled=settings.experiments,
            ),
            queue=queue,
        )
        resumed = queue.resume(session_factory)
        if resumed:
            logger.info("queued %d PDFs left unfinished by the previous run", resumed)
        try:
            yield
        finally:
            queue.shutdown()
            services_tracer.shutdown()
            services_store.close()
            pdf_storage.close()

    app = FastAPI(
        title="pdf_assistant",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api.include_router(auth.router)
    api.include_router(pdfs.router)
    api.include_router(conversations.router)
    app.include_router(api)

    @app.middleware("http")
    async def no_store_for_api(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Starlette stores the whole multipart body before the endpoint can check the
        # size, so an oversized upload is refused from its declared length up front.
        if request.method == "POST" and request.url.path == "/api/pdfs":
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > settings.max_upload_bytes + _MULTIPART_OVERHEAD:
                return JSONResponse(
                    {"detail": f"PDF je veći od {settings.max_upload_mb} MB."},
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                )
        response: Response = await call_next(request)
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    _serve_client(app, settings.client_dir)
    return app


def _serve_client(app: FastAPI, client_dir: Path) -> None:
    """Serve the built SPA: real files as they are, every other path gets index.html."""
    index = client_dir / "index.html"
    root = client_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def client(path: str) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Nema takve adrese.")
        if not index.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Klijent nije izgrađen: `cd client && npm run build`, ili u razvoju koristi `npm run dev`.",
            )
        candidate = (client_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

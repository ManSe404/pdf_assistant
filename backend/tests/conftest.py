import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from pdf_assistant.api.deps import Services
from pdf_assistant.api.main import create_app
from pdf_assistant.db import Base, make_engine, make_session_factory
from pdf_assistant.documents.storage import PdfStorage
from pdf_assistant.settings import Settings
from pdf_assistant.vectors.qdrant import QdrantStore
from tests.helpers import KeywordEmbedder, RecordingTracer, ScriptedChat, make_pdf


@pytest.fixture(autouse=True)
def _no_settings_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's shell (API keys, DATABASE_URL, ...) must not leak into tests."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    for name in list(os.environ):
        if name.startswith("LANGFUSE_"):
            monkeypatch.delenv(name, raising=False)


def make_settings(tmp_path: Path, **values: Any) -> Settings:
    defaults: dict[str, Any] = {"data_dir": tmp_path / "data", "client_dir": tmp_path / "no-client"}
    return Settings(_env_file=None, **{**defaults, **values})  # type: ignore[call-arg]


@dataclass
class App:
    client: TestClient
    settings: Settings
    embedder: KeywordEmbedder
    models: dict[str, ScriptedChat]
    tracer: RecordingTracer

    @property
    def services(self) -> Services:
        services: Services = self.client.app.state.services  # type: ignore[attr-defined]
        return services

    def wait_indexed(self) -> None:
        assert self.services.queue.wait_idle(timeout=30)

    def signup(self, email: str = "ana@example.com", password: str = "lozinka123") -> dict[str, Any]:
        response = self.client.post("/api/auth/signup", json={"email": email, "password": password})
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body

    def upload(self, pages: list[str], name: str = "ugovor.pdf", *, wait: bool = True) -> dict[str, Any]:
        response = self.client.post("/api/pdfs", files={"file": (name, make_pdf(pages), "application/pdf")})
        assert response.status_code == 201, response.text
        if wait:
            self.wait_indexed()
            response = self.client.get(f"/api/pdfs/{response.json()['id']}")
        body: dict[str, Any] = response.json()
        return body


def start_app(tmp_path: Path, *, storage: PdfStorage | None = None, **settings_values: Any) -> tuple[TestClient, App]:
    settings = make_settings(tmp_path, **settings_values)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(f"sqlite:///{settings.data_dir / 'test.db'}")
    Base.metadata.create_all(engine)
    models = {
        "anthropic:claude-opus-5-5": ScriptedChat("claude-opus-5-5"),
        "anthropic:claude-sonnet-5-5": ScriptedChat("claude-sonnet-5-5"),
    }
    embedder = KeywordEmbedder()
    tracer = RecordingTracer()
    app = create_app(
        settings,
        sessions=make_session_factory(engine),
        chat_models=models,  # type: ignore[arg-type]
        embedder=embedder,
        store=QdrantStore(QdrantClient(":memory:"), "test", embedded=True),
        tracer=tracer,
        storage=storage,
    )
    client = TestClient(app)
    return client, App(client, settings, embedder, models, tracer)


@pytest.fixture
def app(tmp_path: Path) -> Iterator[App]:
    client, wrapped = start_app(tmp_path)
    with client:
        yield wrapped

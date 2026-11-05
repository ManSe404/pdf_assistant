"""Migrations, tracing and serving the built client."""

import subprocess
import sys
from pathlib import Path
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from pdf_assistant.db import Base, make_engine
from pdf_assistant.settings import Settings
from pdf_assistant.tracing import LangfuseTracer, NoTracer, build_tracer
from tests.conftest import make_settings, start_app

BACKEND = Path(__file__).resolve().parents[1]


def test_migrations_build_exactly_the_models(tmp_path: Path) -> None:
    env = {"DATA_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    engine = make_engine(f"sqlite:///{tmp_path / 'pdf_assistant.db'}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []


# ------------------------------------------------------------------ tracing


class _FakeObservation:
    def __init__(self, log: list[Any], name: str) -> None:
        self.log, self.name = log, name

    def start_observation(self, **kwargs: Any) -> _FakeObservation:
        self.log.append(("start", kwargs["name"], kwargs.get("as_type"), kwargs.get("model")))
        return _FakeObservation(self.log, kwargs["name"])

    def update(self, **kwargs: Any) -> None:
        self.log.append(("update", self.name, kwargs))

    def end(self) -> None:
        self.log.append(("end", self.name))


class _FakeLangfuse(_FakeObservation):
    def shutdown(self) -> None:
        self.log.append(("shutdown",))


def test_langfuse_tracer_starts_and_ends_each_observation() -> None:
    log: list[Any] = []
    tracer = LangfuseTracer(_FakeLangfuse(log, "client"))
    trace = tracer.start("chat-turn", user_id="u1", session_id="c1", input="Rok?")
    answer = trace.child("answer", as_type="generation", model="claude-opus-5-5", input=[])
    answer.end(output="30 dana")
    trace.end(error="boom")
    tracer.shutdown()
    assert log == [
        ("start", "chat-turn", "chain", None),
        ("start", "answer", "generation", "claude-opus-5-5"),
        ("update", "answer", {"output": "30 dana"}),
        ("end", "answer"),
        ("update", "chat-turn", {"level": "ERROR", "status_message": "boom"}),
        ("end", "chat-turn"),
        ("shutdown",),
    ]


def test_a_broken_tracer_never_breaks_the_caller() -> None:
    class Broken:
        def start_observation(self, **kwargs: Any) -> Any:
            raise RuntimeError("langfuse down")

    trace = LangfuseTracer(Broken()).start("chat-turn", user_id="u1")
    trace.child("answer").end(output="x")  # no-ops, no exception
    trace.end(output="x")


def test_tracing_is_off_without_keys(tmp_path: Path) -> None:
    assert isinstance(build_tracer(make_settings(tmp_path)), NoTracer)
    settings = make_settings(tmp_path, langfuse_public_key="pk-lf-x", langfuse_secret_key="sk-lf-x")
    assert settings.tracing_enabled


# ------------------------------------------------------------------ the built client


def test_the_built_client_is_served_with_a_spa_fallback(tmp_path: Path) -> None:
    client_dir = tmp_path / "build"
    (client_dir / "_app").mkdir(parents=True)
    (client_dir / "index.html").write_text("<html>app</html>")
    (client_dir / "_app" / "main.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("not public")
    client, _ = start_app(tmp_path, client_dir=client_dir)
    with client:
        assert client.get("/").text == "<html>app</html>"
        assert client.get("/documents/123").text == "<html>app</html>"  # client-side route
        assert client.get("/_app/main.js").text == "console.log(1)"
        assert client.get("/../secret.txt").text != "not public"
        assert client.get("/%2e%2e/secret.txt").text != "not public"
        assert client.get("/api/unknown").status_code == 404


def test_without_a_build_the_root_explains_how_to_get_one(tmp_path: Path) -> None:
    client, _ = start_app(tmp_path)
    with client:
        response = client.get("/")
        assert response.status_code == 404 and "npm run build" in response.json()["detail"]


def test_settings_default_to_local_files(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)  # type: ignore[call-arg]
    assert settings.sqlalchemy_url == f"sqlite:///{tmp_path / 'pdf_assistant.db'}"
    assert settings.pdf_dir == tmp_path / "pdfs"

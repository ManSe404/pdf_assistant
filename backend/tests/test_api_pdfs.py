from pathlib import Path

import pytest
from sqlalchemy import select

from pdf_assistant.db import session_scope
from pdf_assistant.documents.indexing import NO_TEXT
from pdf_assistant.documents.storage import PdfFileMissing
from pdf_assistant.models import Pdf, PdfStatus, Vote
from tests.conftest import App, start_app
from tests.helpers import make_pdf

CONTRACT = [
    "UGOVOR O ZAKUPU\nZakupac placa zakupninu do petog u mesecu.",
    "Rok za otkaz je 30 dana od dana prijema pisanog obavestenja.",
    "Depozit iznosi dve mesecne zakupnine i vraca se po isteku ugovora.",
]


def test_upload_indexes_the_pdf_in_the_background(app: App) -> None:
    app.signup()
    pdf = app.upload(CONTRACT)
    assert pdf["status"] == "ready" and pdf["error"] is None
    assert pdf["pages"] == 3 and pdf["chunks"] == 3
    assert pdf["name"] == "ugovor.pdf" and pdf["size_bytes"] > 0
    assert pdf["created_at"].endswith("Z") or "+00:00" in pdf["created_at"]
    assert any("30 dana" in text for text in app.embedder.documents)
    assert app.client.get("/api/pdfs").json() == [pdf]

    [trace] = app.tracer.traces
    assert trace.name == "index-pdf" and trace.ends == [{"output": {"pages": 3, "chunks": 3}, "error": None}]
    [embed] = trace.children
    assert embed.kind == "embedding" and embed.model == "keyword-test-embedder"


def test_the_file_is_served_back_inline(app: App) -> None:
    app.signup()
    pdf = app.upload(CONTRACT)
    response = app.client.get(f"/api/pdfs/{pdf['id']}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == make_pdf(CONTRACT)


def test_uploads_that_are_not_pdfs_or_too_large_are_rejected(tmp_path: Path) -> None:
    client, app = start_app(tmp_path, max_upload_mb=1)
    with client:
        app.signup()
        not_pdf = client.post("/api/pdfs", files={"file": ("slika.pdf", b"\x89PNG not a pdf", "application/pdf")})
        assert not_pdf.status_code == 400 and not_pdf.json()["detail"] == "Fajl nije PDF."
        big = make_pdf(["x"]) + b"0" * (1024 * 1024)
        too_large = client.post("/api/pdfs", files={"file": ("veliki.pdf", big, "application/pdf")})
        assert too_large.status_code == 413
        # A declared length far past the limit is refused before the body is read.
        huge = client.post(
            "/api/pdfs",
            content=b"x",
            headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(50 * 1024 * 1024)},
        )
        assert huge.status_code == 413 and huge.json()["detail"] == "PDF je veći od 1 MB."
        assert client.get("/api/pdfs").json() == []
        assert [p.name for p in app.settings.pdf_dir.iterdir()] == []  # no partial files left


def test_a_pdf_without_text_fails_with_an_explanation(app: App) -> None:
    app.signup()
    pdf = app.upload(["", ""], name="sken.pdf")
    assert pdf["status"] == "failed" and pdf["error"] == NO_TEXT
    assert pdf["pages"] is None


def test_an_embedding_failure_is_shown_on_the_pdf(app: App) -> None:
    app.signup()
    app.embedder.fail_documents = True
    pdf = app.upload(CONTRACT)
    assert pdf["status"] == "failed"
    assert pdf["error"].startswith("Model za embedding nije uspeo") and "401" in pdf["error"]


def test_the_name_is_the_bare_file_name(app: App) -> None:
    app.signup()
    response = app.client.post(
        "/api/pdfs", files={"file": ("C:\\Users\\ana\\Desktop\\plan.pdf", make_pdf(["plan"]), "application/pdf")}
    )
    assert response.json()["name"] == "plan.pdf"


def test_other_users_pdfs_do_not_exist(app: App) -> None:
    app.signup("ana@example.com")
    pdf = app.upload(CONTRACT)
    app.client.post("/api/auth/signout")
    app.signup("marko@example.com")

    assert app.client.get("/api/pdfs").json() == []
    for method, url in [
        ("get", f"/api/pdfs/{pdf['id']}"),
        ("get", f"/api/pdfs/{pdf['id']}/file"),
        ("delete", f"/api/pdfs/{pdf['id']}"),
        ("get", f"/api/pdfs/{pdf['id']}/conversations"),
        ("post", f"/api/pdfs/{pdf['id']}/conversations"),
    ]:
        assert app.client.request(method, url).status_code == 404, url


def test_delete_removes_file_vectors_and_conversations_but_keeps_votes(app: App) -> None:
    app.signup()
    pdf = app.upload(CONTRACT)
    conversation = app.client.post(f"/api/pdfs/{pdf['id']}/conversations").json()
    lines = app.client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "Rok za otkaz?"})
    answer_id = next(line for line in lines.iter_lines() if '"type": "end"' in line).split('"id": "')[1].split('"')[0]
    assert app.client.put(f"/api/messages/{answer_id}/vote", json={"score": 1}).status_code == 200

    assert app.client.delete(f"/api/pdfs/{pdf['id']}").status_code == 204
    assert app.client.get(f"/api/pdfs/{pdf['id']}").status_code == 404
    assert app.client.delete(f"/api/conversations/{conversation['id']}").status_code == 404
    with pytest.raises(PdfFileMissing):
        app.services.storage.read(pdf["id"])
    assert app.services.store.search(pdf["id"], app.embedder.embed_query("rok"), 5) == []
    with session_scope(app.services.sessions) as db:
        [vote] = db.scalars(select(Vote)).all()
        assert vote.message_id is None and vote.score == 1  # the experiment keeps its data


def test_pdfs_left_processing_are_indexed_on_the_next_start(tmp_path: Path) -> None:
    client, app = start_app(tmp_path)
    with client:
        app.signup()
        pdf = app.upload(CONTRACT)
        with session_scope(app.services.sessions) as db:
            row = db.get(Pdf, pdf["id"])
            assert row is not None
            row.status, row.pages, row.chunks = PdfStatus.PROCESSING, None, None

    client, app = start_app(tmp_path)  # same data directory, as after a restart
    with client:
        app.wait_indexed()
        assert app.client.cookies.get("pdfa_session") is None
        app.client.post("/api/auth/signin", json={"email": "ana@example.com", "password": "lozinka123"})
        assert app.client.get(f"/api/pdfs/{pdf['id']}").json()["status"] == "ready"

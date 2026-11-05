"""PDF storage: the same contract on disk and in Supabase Storage.

The Supabase cases run against a real stack when SUPABASE_TEST_URL and
SUPABASE_TEST_SECRET_KEY are set, e.g. after ``npx supabase start`` in the repo root:

    SUPABASE_TEST_URL=http://127.0.0.1:54321 SUPABASE_TEST_SECRET_KEY=sb_secret_... uv run pytest -k storage

Each run uses its own bucket and removes it afterwards.
"""

import io
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

import pytest

from pdf_assistant.documents.storage import (
    DiskStorage,
    PdfFileMissing,
    PdfStorage,
    StorageError,
    SupabaseStorage,
    UploadRejected,
    build_pdf_storage,
)
from pdf_assistant.settings import PdfStorageKind
from tests.conftest import make_settings, start_app
from tests.helpers import make_pdf

MB = 1024 * 1024
SUPABASE_URL = os.environ.get("SUPABASE_TEST_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_TEST_SECRET_KEY")


def _supabase(tmp_path: Path, url: str, key: str, bucket: str) -> SupabaseStorage:
    settings = make_settings(
        tmp_path, pdf_storage="supabase", supabase_url=url, supabase_secret_key=key, supabase_bucket=bucket
    )
    storage = build_pdf_storage(settings)
    assert isinstance(storage, SupabaseStorage)
    return storage


@pytest.fixture(params=["disk", "supabase"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[PdfStorage]:
    if request.param == "disk":
        yield DiskStorage(tmp_path / "pdfs")
        return
    if not (SUPABASE_URL and SUPABASE_KEY):
        pytest.skip("set SUPABASE_TEST_URL and SUPABASE_TEST_SECRET_KEY to run")
    bucket = f"test-{uuid.uuid4().hex[:8]}"
    supabase = _supabase(tmp_path, SUPABASE_URL, SUPABASE_KEY, bucket)
    try:
        yield supabase
    finally:
        client = supabase._client
        try:
            client.empty_bucket(bucket)
            client.delete_bucket(bucket)
        except Exception:  # noqa: BLE001 - the bucket was never created
            pass
        supabase.close()


def test_save_read_and_delete(storage: PdfStorage) -> None:
    pdf = make_pdf(["Prva strana."])
    assert storage.save("a", io.BytesIO(pdf), max_bytes=MB) == len(pdf)
    assert storage.read("a") == pdf
    replacement = make_pdf(["Druga verzija."])
    storage.save("a", io.BytesIO(replacement), max_bytes=MB)
    assert storage.read("a") == replacement
    storage.delete("a")
    with pytest.raises(PdfFileMissing):
        storage.read("a")
    storage.delete("a")  # deleting twice is fine


def test_rejected_uploads_leave_nothing_behind(storage: PdfStorage) -> None:
    with pytest.raises(UploadRejected, match="nije PDF"):
        storage.save("b", io.BytesIO(b"GIF89a" + b"0" * 4000), max_bytes=MB)
    with pytest.raises(UploadRejected) as too_large:
        storage.save("b", io.BytesIO(make_pdf(["x"]) + b"0" * MB), max_bytes=MB)
    assert too_large.value.too_large
    with pytest.raises(PdfFileMissing):
        storage.read("b")


def test_a_few_bytes_before_the_header_are_allowed(storage: PdfStorage) -> None:
    pdf = b"\xef\xbb\xbf" + make_pdf(["x"])
    storage.save("c", io.BytesIO(pdf), max_bytes=MB)
    assert storage.read("c") == pdf


@pytest.mark.skipif(not (SUPABASE_URL and SUPABASE_KEY), reason="set SUPABASE_TEST_URL and SUPABASE_TEST_SECRET_KEY")
def test_supabase_creates_a_private_pdf_bucket(tmp_path: Path) -> None:
    assert SUPABASE_URL and SUPABASE_KEY
    bucket = f"test-{uuid.uuid4().hex[:8]}"
    storage = _supabase(tmp_path, SUPABASE_URL, SUPABASE_KEY, bucket)
    try:
        storage.save("d", io.BytesIO(make_pdf(["x"])), max_bytes=MB)
        created = storage._client.get_bucket(bucket)
        assert created.public is False
        assert created.allowed_mime_types == ["application/pdf"]
    finally:
        storage._client.empty_bucket(bucket)
        storage._client.delete_bucket(bucket)
        storage.close()


def test_supabase_needs_url_and_key(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="SUPABASE_URL and SUPABASE_SECRET_KEY"):
        build_pdf_storage(make_settings(tmp_path, pdf_storage="supabase"))
    assert isinstance(build_pdf_storage(make_settings(tmp_path)), DiskStorage)
    assert make_settings(tmp_path).pdf_storage is PdfStorageKind.DISK


def test_an_unreachable_supabase_is_a_storage_error(tmp_path: Path) -> None:
    storage = _supabase(tmp_path, "http://127.0.0.1:9", "sb_secret_test", "pdfs")
    try:
        with pytest.raises(StorageError):
            storage.save("e", io.BytesIO(make_pdf(["x"])), max_bytes=MB)
        with pytest.raises(StorageError):
            storage.read("e")
        with pytest.raises(StorageError):
            storage.delete("e")
    finally:
        storage.close()


def test_postgres_urls_get_the_installed_driver(tmp_path: Path) -> None:
    url = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    assert make_settings(tmp_path, database_url=url).sqlalchemy_url.startswith("postgresql+psycopg://postgres:")
    assert make_settings(tmp_path, database_url="postgres://u:p@h/db").sqlalchemy_url == "postgresql+psycopg://u:p@h/db"
    explicit = "postgresql+psycopg://u:p@h/db"
    assert make_settings(tmp_path, database_url=explicit).sqlalchemy_url == explicit


# ------------------------------------------------------------------ the API when storage fails


class BrokenStorage:
    """Disk storage that fails on demand, as Supabase does when it is down."""

    def __init__(self, directory: Path) -> None:
        self.disk = DiskStorage(directory)
        self.down = False
        self.failing_reads: Exception | None = None  # only reads fail (uploads still work)

    def _check(self) -> None:
        if self.down:
            raise StorageError("Supabase Storage is down")

    def save(self, pdf_id: str, source: BinaryIO, *, max_bytes: int) -> int:
        self._check()
        return self.disk.save(pdf_id, source, max_bytes=max_bytes)

    def read(self, pdf_id: str) -> bytes:
        self._check()
        if self.failing_reads:
            raise self.failing_reads
        return self.disk.read(pdf_id)

    def delete(self, pdf_id: str) -> None:
        self._check()
        self.disk.delete(pdf_id)

    def close(self) -> None:
        pass


def test_the_api_answers_503_while_storage_is_down_and_recovers(tmp_path: Path) -> None:
    broken = BrokenStorage(tmp_path / "pdfs")
    client, app = start_app(tmp_path, storage=broken)
    with client:
        app.signup()
        pdf = app.upload(["Rok za otkaz je 30 dana."])
        assert app.client.get(f"/api/pdfs/{pdf['id']}/file").status_code == 200

        broken.down = True
        upload = app.client.post("/api/pdfs", files={"file": ("novi.pdf", make_pdf(["x"]), "application/pdf")})
        assert upload.status_code == 503 and "Skladište" in upload.json()["detail"]
        assert [p["id"] for p in app.client.get("/api/pdfs").json()] == [pdf["id"]]  # no row without a file
        assert app.client.get(f"/api/pdfs/{pdf['id']}/file").status_code == 503
        # Deleting still removes the PDF; the file left behind is never served.
        assert app.client.delete(f"/api/pdfs/{pdf['id']}").status_code == 204

        broken.down = False
        again = app.upload(["Depozit su dve zakupnine."])
        assert again["status"] == "ready"


def test_indexing_fails_with_a_reason_when_the_file_cannot_be_read(tmp_path: Path) -> None:
    broken = BrokenStorage(tmp_path / "pdfs")
    client, app = start_app(tmp_path, storage=broken)
    with client:
        app.signup()
        broken.failing_reads = PdfFileMissing("gone")
        missing = app.upload(["Rok za otkaz je 30 dana."])
        assert missing["status"] == "failed" and "više ne postoji" in missing["error"]
        assert app.client.get(f"/api/pdfs/{missing['id']}/file").status_code == 404

        broken.failing_reads = StorageError("Supabase Storage download failed: timed out")
        down = app.upload(["Depozit."])
        assert down["status"] == "failed" and "Skladište PDF-ova nije uspelo" in down["error"]

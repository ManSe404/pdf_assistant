"""Where uploaded PDFs live: a folder on disk (the default) or a Supabase Storage bucket.

Both keep one object per PDF, ``<id>.pdf``. The rest of the app needs only save, read
and delete, so another backend is one more small class.
"""

import logging
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Protocol

import httpx

from pdf_assistant.settings import PdfStorageKind, Settings

if TYPE_CHECKING:
    from storage3 import SyncStorageClient

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
PDF_MIME = "application/pdf"
_COPY_CHUNK = 1024 * 1024
_TIMEOUT_SECONDS = 60


class UploadRejected(Exception):
    def __init__(self, message: str, *, too_large: bool = False) -> None:
        super().__init__(message)
        self.too_large = too_large


class StorageError(Exception):
    """The storage could not be reached or refused the operation."""


class PdfFileMissing(Exception):
    """The PDF's row exists but its file does not."""


class PdfStorage(Protocol):
    def save(self, pdf_id: str, source: BinaryIO, *, max_bytes: int) -> int:
        """Store an upload; return its size. Rejects non-PDFs and oversized files
        without leaving anything behind."""
        ...

    def read(self, pdf_id: str) -> bytes: ...

    def delete(self, pdf_id: str) -> None:
        """Remove the file; a missing file is not an error."""
        ...

    def close(self) -> None: ...


def checked_chunks(source: BinaryIO, max_bytes: int) -> Iterator[bytes]:
    """The upload in chunks, after checking that it is a PDF and as long as it stays
    within ``max_bytes``."""
    head = source.read(len(PDF_MAGIC))
    # Some generators put a few bytes before the header; the spec allows 1024.
    if head != PDF_MAGIC:
        rest = source.read(1024)
        if PDF_MAGIC not in head + rest:
            raise UploadRejected("Fajl nije PDF.")
        head += rest
    size = 0
    chunk = head
    while chunk:
        size += len(chunk)
        if size > max_bytes:
            raise UploadRejected(f"PDF je veći od {max_bytes // (1024 * 1024)} MB.", too_large=True)
        yield chunk
        chunk = source.read(_COPY_CHUNK)


def _object_name(pdf_id: str) -> str:
    return f"{pdf_id}.pdf"


class DiskStorage:
    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, pdf_id: str) -> Path:
        return self._dir / _object_name(pdf_id)

    def save(self, pdf_id: str, source: BinaryIO, *, max_bytes: int) -> int:
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, suffix=".part")
        size = 0
        try:
            with os.fdopen(fd, "wb") as out:
                for chunk in checked_chunks(source, max_bytes):
                    out.write(chunk)
                    size += len(chunk)
            os.replace(tmp_name, self._path(pdf_id))
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return size

    def read(self, pdf_id: str) -> bytes:
        try:
            return self._path(pdf_id).read_bytes()
        except FileNotFoundError:
            raise PdfFileMissing(pdf_id) from None

    def delete(self, pdf_id: str) -> None:
        self._path(pdf_id).unlink(missing_ok=True)

    def close(self) -> None:
        pass


class SupabaseStorage:
    """A private Supabase Storage bucket, read and written only by the backend.

    Works the same against a local stack (``npx supabase start``) and a Supabase Cloud
    project. The bucket is created on the first upload when it does not exist yet.
    """

    def __init__(self, client: SyncStorageClient, bucket: str, *, max_bytes: int) -> None:
        self._client = client
        self._bucket = bucket
        self._max_bytes = max_bytes
        self._bucket_ready = False
        self._lock = threading.Lock()

    def save(self, pdf_id: str, source: BinaryIO, *, max_bytes: int) -> int:
        # Supabase takes the whole body; uploads are capped at MAX_UPLOAD_MB anyway.
        data = b"".join(checked_chunks(source, max_bytes))
        with _storage_errors("upload"):
            self._ensure_bucket()
            self._client.from_(self._bucket).upload(
                _object_name(pdf_id), data, {"content-type": PDF_MIME, "upsert": "true"}
            )
        return len(data)

    def read(self, pdf_id: str) -> bytes:
        from storage3.exceptions import StorageApiError

        try:
            with _storage_errors("download"):
                return self._client.from_(self._bucket).download(_object_name(pdf_id))
        except StorageError as exc:
            if isinstance(exc.__cause__, StorageApiError) and _is_not_found(exc.__cause__):
                raise PdfFileMissing(pdf_id) from None
            raise

    def delete(self, pdf_id: str) -> None:
        # Removing an object that is not there succeeds with an empty list.
        with _storage_errors("delete"):
            self._client.from_(self._bucket).remove([_object_name(pdf_id)])

    def close(self) -> None:
        self._client.session.close()

    def _ensure_bucket(self) -> None:
        from storage3.exceptions import StorageApiError

        if self._bucket_ready:
            return
        with self._lock:
            if self._bucket_ready:
                return
            try:
                bucket = self._client.get_bucket(self._bucket)
                if bucket.public:
                    logger.warning("Supabase bucket '%s' is public: anyone with a PDF's URL can read it", self._bucket)
            except StorageApiError as exc:
                if not _is_not_found(exc):
                    raise
                try:
                    self._client.create_bucket(
                        self._bucket,
                        options={"public": False, "file_size_limit": self._max_bytes, "allowed_mime_types": [PDF_MIME]},
                    )
                    logger.info("created the private Supabase bucket '%s'", self._bucket)
                except StorageApiError as create_exc:
                    # Another process created it in the meantime.
                    if str(create_exc.status) != "409":
                        raise
            self._bucket_ready = True


@contextmanager
def _storage_errors(action: str) -> Iterator[None]:
    """Turn every failure of the Supabase client into StorageError, keeping the cause."""
    from storage3.utils import StorageException

    try:
        yield
    except (StorageException, httpx.HTTPError) as exc:
        raise StorageError(f"Supabase Storage {action} failed: {exc}") from exc


def _is_not_found(exc: Exception) -> bool:
    return str(getattr(exc, "status", "")) == "404"


def build_pdf_storage(settings: Settings) -> PdfStorage:
    if settings.pdf_storage is PdfStorageKind.SUPABASE:
        from storage3 import SyncStorageClient

        if not (settings.supabase_url and settings.supabase_secret_key):
            raise StorageError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set to use PDF_STORAGE=supabase")
        key = settings.supabase_secret_key.get_secret_value()
        headers = {"apikey": key}
        if key.startswith("eyJ"):
            # A legacy service_role key is a JWT and also goes in Authorization. The new
            # sb_secret_ keys are not JWTs and belong only in apikey.
            headers["Authorization"] = f"Bearer {key}"
        http = httpx.Client(timeout=_TIMEOUT_SECONDS, follow_redirects=True)
        client = SyncStorageClient(f"{settings.supabase_url.rstrip('/')}/storage/v1/", headers, http_client=http)
        return SupabaseStorage(client, settings.supabase_bucket, max_bytes=settings.max_upload_bytes)
    return DiskStorage(settings.pdf_dir)

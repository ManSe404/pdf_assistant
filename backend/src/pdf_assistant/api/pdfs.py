import logging
from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response

from pdf_assistant.api.deps import CurrentUser, ServicesDep
from pdf_assistant.api.schemas import PdfOut
from pdf_assistant.db import session_scope
from pdf_assistant.documents.service import PdfNotFound, get_pdf, list_pdfs
from pdf_assistant.documents.storage import PdfFileMissing, PdfStorage, StorageError, UploadRejected
from pdf_assistant.models import Pdf, new_id
from pdf_assistant.vectors import VectorStoreError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pdfs", tags=["pdfs"])


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="PDF ne postoji.")


def _storage_down(exc: StorageError) -> HTTPException:
    logger.warning("PDF storage failed: %s", exc)
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE, detail="Skladište PDF-ova trenutno ne radi. Pokušaj ponovo."
    )


def _display_name(filename: str | None) -> str:
    # Browsers send a bare name; strip any path a client might add anyway.
    name = PurePath((filename or "").replace("\\", "/")).name.strip()
    return (name or "dokument.pdf")[:255]


@router.get("")
def list_all(user: CurrentUser, services: ServicesDep) -> list[PdfOut]:
    with session_scope(services.sessions) as db:
        return [PdfOut.of(p) for p in list_pdfs(db, user.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
def upload(file: UploadFile, user: CurrentUser, services: ServicesDep) -> PdfOut:
    pdf_id = new_id()
    try:
        size = services.storage.save(pdf_id, file.file, max_bytes=services.settings.max_upload_bytes)
    except UploadRejected as exc:
        code = status.HTTP_413_CONTENT_TOO_LARGE if exc.too_large else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, detail=str(exc)) from None
    except StorageError as exc:
        raise _storage_down(exc) from None
    try:
        with session_scope(services.sessions) as db:
            pdf = Pdf(id=pdf_id, user_id=user.id, name=_display_name(file.filename), size_bytes=size)
            db.add(pdf)
            db.flush()
            out = PdfOut.of(pdf)
    except BaseException:
        _delete_file(services.storage, pdf_id)
        raise
    services.queue.submit(pdf_id)
    return out


@router.get("/{pdf_id}")
def show(pdf_id: str, user: CurrentUser, services: ServicesDep) -> PdfOut:
    try:
        with session_scope(services.sessions) as db:
            return PdfOut.of(get_pdf(db, user.id, pdf_id))
    except PdfNotFound:
        raise _not_found() from None


@router.get("/{pdf_id}/file", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def download(pdf_id: str, user: CurrentUser, services: ServicesDep) -> Response:
    try:
        with session_scope(services.sessions) as db:
            name = get_pdf(db, user.id, pdf_id).name
    except PdfNotFound:
        raise _not_found() from None
    try:
        content = services.storage.read(pdf_id)
    except PdfFileMissing:
        raise _not_found() from None
    except StorageError as exc:
        raise _storage_down(exc) from None
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": _inline(name)})


def _inline(filename: str) -> str:
    quoted = quote(filename)
    if quoted == filename:
        return f'inline; filename="{filename}"'
    return f"inline; filename*=utf-8''{quoted}"


def _delete_file(storage: PdfStorage, pdf_id: str) -> None:
    try:
        storage.delete(pdf_id)
    except StorageError:
        # The row is gone; an orphaned file is never served or searched.
        logger.warning("could not delete the file of PDF %s", pdf_id, exc_info=True)


@router.delete("/{pdf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(pdf_id: str, user: CurrentUser, services: ServicesDep) -> None:
    try:
        with session_scope(services.sessions) as db:
            db.delete(get_pdf(db, user.id, pdf_id))
    except PdfNotFound:
        raise _not_found() from None
    _delete_file(services.storage, pdf_id)
    try:
        services.store.delete(pdf_id)
    except VectorStoreError:
        # The rows and the file are gone; leftover vectors are never searched again.
        logger.warning("could not delete the vectors of PDF %s", pdf_id, exc_info=True)

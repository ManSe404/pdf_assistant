"""PDF rows of one user. Every lookup is scoped to the owner; another user's PDF is
"not found", never "forbidden", so ids reveal nothing."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from pdf_assistant.models import Pdf


class PdfNotFound(Exception):
    pass


def list_pdfs(db: Session, user_id: str) -> list[Pdf]:
    return list(db.scalars(select(Pdf).where(Pdf.user_id == user_id).order_by(Pdf.created_at.desc())))


def get_pdf(db: Session, user_id: str, pdf_id: str) -> Pdf:
    pdf = db.get(Pdf, pdf_id)
    if pdf is None or pdf.user_id != user_id:
        raise PdfNotFound(pdf_id)
    return pdf

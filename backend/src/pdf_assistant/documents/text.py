"""PDF text, page by page, and chunks that remember the page they start on.

Chunks follow the text's own boundaries where they can: paragraphs, then lines, then
sentences, then words; only a word longer than the chunk is cut. Consecutive chunks of
a page overlap by about ``overlap`` characters so an answer split across a boundary is
still found whole in one of them.
"""

import re
from collections.abc import Sequence
from pathlib import Path

import pypdfium2 as pdfium

from pdf_assistant.vectors.base import Chunk

_SEPARATORS = ("\n\n", "\n", ". ", " ")
_SPACES = re.compile("[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class PdfUnreadable(Exception):
    pass


def read_pages(source: Path | bytes) -> list[str]:
    """The text of every page; an empty string for a page without a text layer."""
    try:
        document = pdfium.PdfDocument(source)
    except pdfium.PdfiumError as exc:
        raise PdfUnreadable(f"PDF se ne može otvoriti ({exc}).") from exc
    try:
        pages = []
        for index in range(len(document)):
            page = document[index]
            try:
                textpage = page.get_textpage()
                try:
                    pages.append(clean(textpage.get_text_bounded()))
                finally:
                    textpage.close()
            finally:
                page.close()
        return pages
    finally:
        document.close()


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()


def _split(text: str, size: int, separators: Sequence[str]) -> list[str]:
    """Pieces no longer than ``size``, split at the coarsest separator that works."""
    if len(text) <= size:
        return [text]
    if not separators:
        return [text[i : i + size] for i in range(0, len(text), size)]
    sep, finer = separators[0], separators[1:]
    parts = text.split(sep)
    pieces: list[str] = []
    for i, part in enumerate(parts):
        part = part + sep if i < len(parts) - 1 else part
        if len(part) > size:
            pieces.extend(_split(part, size, finer))
        elif part:
            pieces.append(part)
    return pieces


def chunk_page(text: str, *, size: int, overlap: int) -> list[str]:
    pieces = _split(text, size, _SEPARATORS)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > size:
            chunks.append(current.strip())
            # Carry the tail of the previous chunk, starting at a word boundary.
            tail = current[-overlap:] if overlap else ""
            if " " in tail:
                tail = tail[tail.index(" ") + 1 :]
            current = tail if len(tail) + len(piece) <= size else ""
        current += piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_pages(pages: Sequence[str], *, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_number, text in enumerate(pages, start=1):
        for piece in chunk_page(text, size=size, overlap=overlap):
            chunks.append(Chunk(index=len(chunks), page=page_number, text=piece))
    return chunks

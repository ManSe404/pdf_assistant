import asyncio
import itertools
from pathlib import Path

import pytest

from pdf_assistant.chat import rag
from pdf_assistant.documents.text import PdfUnreadable, chunk_page, chunk_pages, clean, read_pages
from pdf_assistant.vectors import Hit
from tests.helpers import ScriptedChat, make_pdf


def test_read_pages_returns_one_text_per_page(tmp_path: Path) -> None:
    path = tmp_path / "a.pdf"
    path.write_bytes(make_pdf(["Prva strana\ndrugi red", "", "Treca strana"]))
    assert read_pages(path) == ["Prva strana\ndrugi red", "", "Treca strana"]


def test_an_unreadable_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nthis is not really a pdf")
    with pytest.raises(PdfUnreadable):
        read_pages(path)


def test_clean_normalizes_whitespace() -> None:
    assert clean("a\u00a0 \tb\r\n\r\n\r\n\r\nc\x00") == "a b\n\nc"


def test_chunks_respect_the_size_and_overlap_at_word_boundaries() -> None:
    text = " ".join(f"rec{i}" for i in range(400))  # ~2.4k characters, no paragraphs
    chunks = chunk_page(text, size=500, overlap=100)
    assert len(chunks) > 4
    assert all(len(c) <= 500 for c in chunks)
    for previous, current in itertools.pairwise(chunks):
        first_word = current.split()[0]
        assert first_word in previous.split()  # the overlap starts on a whole word
    words = [w for c in chunks for w in c.split()]
    assert set(words) == {f"rec{i}" for i in range(400)}  # nothing lost


def test_chunks_prefer_paragraph_boundaries() -> None:
    text = "Prvi pasus ima recenicu.\n\nDrugi pasus je ovde.\n\nTreci."
    # Small pieces are packed together up to the size, split where a paragraph ends.
    assert chunk_page(text, size=30, overlap=0) == ["Prvi pasus ima recenicu.", "Drugi pasus je ovde.\n\nTreci."]
    assert chunk_page(text, size=25, overlap=0) == ["Prvi pasus ima recenicu.", "Drugi pasus je ovde.", "Treci."]


def test_a_word_longer_than_the_chunk_is_cut() -> None:
    assert chunk_page("x" * 25, size=10, overlap=0) == ["x" * 10, "x" * 10, "x" * 5]


def test_chunks_remember_their_page_and_skip_empty_pages() -> None:
    chunks = chunk_pages(["prva", "", "treca"], size=100, overlap=10)
    assert [(c.index, c.page, c.text) for c in chunks] == [(0, 1, "prva"), (1, 3, "treca")]


def _hit(page: int, text: str) -> Hit:
    return Hit(index=page, page=page, text=text, score=1.0)


def test_the_prompt_keeps_passages_then_whole_turns_within_the_budget() -> None:
    hits = [_hit(1, "a" * 400), _hit(2, "b" * 400), _hit(3, "c" * 4000)]
    old_turn = [{"role": "user", "content": "x" * 500}, {"role": "assistant", "content": "y" * 500}]
    new_turn = [{"role": "user", "content": "z" * 40}, {"role": "assistant", "content": "w" * 40}]
    prompt = rag.build_prompt("pitanje?", hits, [*old_turn, *new_turn], max_prompt_tokens=600)
    assert [h.page for h in prompt.used] == [1, 2]  # the third passage does not fit
    assert "[1] (page 1)" in prompt.system and "[2] (page 2)" in prompt.system
    # The newest turn fits, the older one would not: it goes out whole, never half.
    assert prompt.messages == [*new_turn, {"role": "user", "content": "pitanje?"}]

    roomy = rag.build_prompt("pitanje?", hits[:2], [*old_turn, *new_turn], max_prompt_tokens=10_000)
    assert roomy.messages == [*old_turn, *new_turn, {"role": "user", "content": "pitanje?"}]


def test_recent_history_keeps_whole_turns() -> None:
    history = [{"role": r, "content": str(i)} for i, r in enumerate(["user", "assistant"] * 3)]
    assert rag.recent_history(history, 0) == history
    assert rag.recent_history(history, 1) == history[-2:]


def test_cited_sources_keep_prompt_numbers() -> None:
    used = [_hit(4, "cetiri"), _hit(9, "devet"), _hit(2, "dva")]
    sources = rag.cited_sources(used, "Prvo [3], pa [1][3].")
    assert sources == [{"n": 1, "page": 4, "text": "cetiri"}, {"n": 3, "page": 2, "text": "dva"}]
    assert rag.cited_sources(used, "Dokument to ne navodi.") == []
    assert rag.cited_sources(used, "Vidi [7].") == []  # a number the prompt never had


def test_the_rewrite_falls_back_to_the_question() -> None:
    history = [{"role": "user", "content": "Rok?"}, {"role": "assistant", "content": "30 dana."}]
    model = ScriptedChat("m", rewrite="  Koliki je   rok za otkaz?  ")
    assert asyncio.run(rag.standalone_question("A otkaz?", history, model)) == "Koliki je rok za otkaz?"
    model.rewrite = ""
    assert asyncio.run(rag.standalone_question("A otkaz?", history, model)) == "A otkaz?"
    model.rewrite = "x" * 2000
    assert asyncio.run(rag.standalone_question("A otkaz?", history, model)) == "A otkaz?"
    assert asyncio.run(rag.standalone_question("A otkaz?", [], model)) == "A otkaz?"

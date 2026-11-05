import json
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import App, start_app
from tests.test_api_pdfs import CONTRACT


def _ask(app: App, conversation_id: str, question: str) -> list[dict[str, Any]]:
    response = app.client.post(f"/api/conversations/{conversation_id}/messages", json={"content": question})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.iter_lines() if line]


def _start(app: App) -> tuple[dict[str, Any], dict[str, Any]]:
    app.signup()
    pdf = app.upload(CONTRACT)
    conversation = app.client.post(f"/api/pdfs/{pdf['id']}/conversations").json()
    return pdf, conversation


def _model(app: App, conversation: dict[str, Any]):  # type: ignore[no-untyped-def]
    return app.models[conversation["components"]["llm"]["name"]]


def test_a_new_conversation_gets_one_component_of_each_kind(app: App) -> None:
    pdf, conversation = _start(app)
    assert conversation["pdf_id"] == pdf["id"] and conversation["messages"] == []
    assert conversation["title"] == "Novi razgovor"
    components = conversation["components"]
    assert components["llm"]["name"] in app.models
    assert components["llm"]["label"] in ("claude-opus-5-5", "claude-sonnet-5-5")
    assert components["retriever"] in [
        {"name": "top_3", "label": "3 isečka"},
        {"name": "top_5", "label": "5 isečaka"},
        {"name": "top_8", "label": "8 isečaka"},
    ]
    assert components["memory"] in [
        {"name": "all_history", "label": "cela istorija"},
        {"name": "last_2_turns", "label": "poslednja 2 pitanja"},
    ]


def test_the_answer_streams_and_is_saved_with_its_cited_pages(app: App) -> None:
    pdf, conversation = _start(app)
    events = _ask(app, conversation["id"], "Koliki je rok za otkaz?")

    assert next(e["type"] for e in events) == "start" and events[-1]["type"] == "end"
    assert events[0]["user_message"]["content"] == "Koliki je rok za otkaz?"
    assert events[0]["title"] == "Koliki je rok za otkaz?"
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    answer = events[-1]["message"]
    assert answer["role"] == "assistant" and answer["content"] == text == "Rok je 30 dana [1]."
    assert answer["vote"] is None
    # The keyword embedder puts the page that mentions "rok" and "otkaz" first.
    assert answer["sources"][0]["n"] == 1 and answer["sources"][0]["page"] == 2
    assert "30 dana" in answer["sources"][0]["text"]

    model = _model(app, conversation)
    [call] = model.streams
    assert "(page 2)" in call["system"] and call["messages"] == [{"role": "user", "content": "Koliki je rok za otkaz?"}]
    assert model.completions == []  # no history: nothing to rewrite

    [listed] = app.client.get(f"/api/pdfs/{pdf['id']}/conversations").json()
    assert listed["title"] == "Koliki je rok za otkaz?"
    assert [m["role"] for m in listed["messages"]] == ["user", "assistant"]
    assert listed["messages"][1] == answer


def test_an_answer_that_cites_nothing_has_no_sources(app: App) -> None:
    _, conversation = _start(app)
    _model(app, conversation).answer = "Dokument to ne navodi."
    events = _ask(app, conversation["id"], "Ko je potpisao?")
    assert events[-1]["message"]["sources"] == []


def test_a_follow_up_is_rewritten_for_retrieval_but_answered_as_asked(app: App) -> None:
    _, conversation = _start(app)
    _ask(app, conversation["id"], "Koliki je rok za otkaz?")
    model = _model(app, conversation)
    model.rewrite = "Koliki je depozit po ugovoru o zakupu?"
    events = _ask(app, conversation["id"], "A depozit?")

    assert events[-1]["type"] == "end"
    [rewrite] = model.completions
    assert "<last_message>\nA depozit?\n</last_message>" in rewrite["messages"][0]["content"]
    assert app.embedder.queries[-1] == "Koliki je depozit po ugovoru o zakupu?"
    last = model.streams[-1]["messages"]
    assert last[-1] == {"role": "user", "content": "A depozit?"}
    assert last[0] == {"role": "user", "content": "Koliki je rok za otkaz?"}


@pytest.mark.parametrize(("memory", "kept"), [("0", 6), ("1", 2)])
def test_the_memory_component_limits_the_history(tmp_path: Path, memory: str, kept: int) -> None:
    client, app = start_app(tmp_path, memory_turns=memory)
    with client:
        _, conversation = _start(app)
        for question in ("Prvo pitanje?", "Drugo pitanje?", "Trece pitanje?", "Cetvrto pitanje?"):
            _ask(app, conversation["id"], question)
        last = _model(app, conversation).streams[-1]["messages"]
        assert len(last) == kept + 1 and last[-1]["content"] == "Cetvrto pitanje?"


def test_a_failed_answer_is_an_error_event_and_is_not_saved(app: App) -> None:
    pdf, conversation = _start(app)
    model = _model(app, conversation)
    model.fail_after = 2
    events = _ask(app, conversation["id"], "Koliki je rok?")
    assert [e["type"] for e in events] == ["start", "delta", "delta", "error"]
    assert events[-1]["detail"].startswith("Model trenutno ne može")

    [stored] = app.client.get(f"/api/pdfs/{pdf['id']}/conversations").json()
    assert [m["role"] for m in stored["messages"]] == ["user"]

    # The unanswered question stays out of the history of the next turn.
    model.fail_after = None
    _ask(app, conversation["id"], "Koliki je depozit?")
    assert model.streams[-1]["messages"] == [{"role": "user", "content": "Koliki je depozit?"}]

    failed, ok = app.tracer.traces[-2], app.tracer.traces[-1]
    assert failed.name == "chat-turn" and failed.ends[0]["error"]
    assert ok.ends == [{"output": "Rok je 30 dana [1].", "error": None}]


def test_the_turn_is_traced_with_its_steps(app: App) -> None:
    _, conversation = _start(app)
    _ask(app, conversation["id"], "Koliki je rok za otkaz?")
    _ask(app, conversation["id"], "A depozit?")
    trace = app.tracer.traces[-1]
    assert trace.name == "chat-turn" and trace.input == "A depozit?"
    assert trace.attributes["session_id"] == conversation["id"]
    assert trace.attributes["llm"] == conversation["components"]["llm"]["name"]
    assert [c.name for c in trace.children] == ["rewrite-followup", "retrieve", "answer"]
    assert [c.kind for c in trace.children] == ["generation", "retriever", "generation"]
    assert all(len(c.ends) == 1 for c in trace.children) and len(trace.ends) == 1


def test_questions_need_a_ready_pdf_and_some_text(app: App) -> None:
    app.signup()
    pdf = app.upload(["", ""])  # fails: no text layer
    conversation = app.client.post(f"/api/pdfs/{pdf['id']}/conversations").json()
    response = app.client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "Rok?"})
    assert response.status_code == 409

    _, ready = _start_second(app)
    blank = app.client.post(f"/api/conversations/{ready['id']}/messages", json={"content": "   "})
    assert blank.status_code == 422 and blank.json()["detail"][0]["msg"] == "Pitanje je prazno."
    long = app.client.post(f"/api/conversations/{ready['id']}/messages", json={"content": "x" * 4001})
    assert long.status_code == 422
    assert app.client.post("/api/conversations/nope/messages", json={"content": "Rok?"}).status_code == 404


def _start_second(app: App) -> tuple[dict[str, Any], dict[str, Any]]:
    pdf = app.upload(CONTRACT)
    return pdf, app.client.post(f"/api/pdfs/{pdf['id']}/conversations").json()


def test_votes_can_be_set_changed_and_cleared(app: App) -> None:
    _, conversation = _start(app)
    events = _ask(app, conversation["id"], "Koliki je rok za otkaz?")
    answer_id = events[-1]["message"]["id"]
    question_id = events[0]["user_message"]["id"]

    assert app.client.put(f"/api/messages/{answer_id}/vote", json={"score": 1}).json()["vote"] == 1
    assert app.client.put(f"/api/messages/{answer_id}/vote", json={"score": -1}).json()["vote"] == -1
    assert app.client.put(f"/api/messages/{question_id}/vote", json={"score": 1}).status_code == 400
    assert app.client.put(f"/api/messages/{answer_id}/vote", json={"score": 5}).status_code == 422

    scores = app.client.get("/api/scores").json()
    llm = {row["name"]: row for row in scores["llm"]}[conversation["components"]["llm"]["name"]]
    assert (llm["up"], llm["down"], llm["satisfaction"]) == (0, 1, 0.0)

    assert app.client.put(f"/api/messages/{answer_id}/vote", json={"score": 0}).json()["vote"] is None
    llm = {row["name"]: row for row in app.client.get("/api/scores").json()["llm"]}[llm["name"]]
    assert (llm["up"], llm["down"], llm["satisfaction"]) == (0, 0, None)


def test_scores_list_every_component_with_its_chance(app: App) -> None:
    _, conversation = _start(app)
    events = _ask(app, conversation["id"], "Koliki je rok za otkaz?")
    app.client.put(f"/api/messages/{events[-1]['message']['id']}/vote", json={"score": -1})

    scores = app.client.get("/api/scores").json()
    assert [r["name"] for r in scores["retriever"]] == ["top_3", "top_5", "top_8"]
    assert [r["name"] for r in scores["memory"]] == ["all_history", "last_2_turns"]
    for kind in ("llm", "retriever", "memory"):
        assert sum(r["weight"] for r in scores[kind]) == pytest.approx(1.0, abs=1e-3)
        downvoted = [r for r in scores[kind] if r["down"]]
        others = [r for r in scores[kind] if not r["down"]]
        assert len(downvoted) == 1
        # One thumbs down halves the weight: (0 + 1) / (0 + 1 + 1) against 1.
        assert all(downvoted[0]["weight"] == pytest.approx(o["weight"] / 2, abs=1e-3) for o in others)


def test_another_users_conversations_and_answers_are_not_reachable(app: App) -> None:
    _, conversation = _start(app)
    answer_id = _ask(app, conversation["id"], "Rok?")[-1]["message"]["id"]
    app.client.post("/api/auth/signout")
    app.signup("marko@example.com")
    assert (
        app.client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "x"}).status_code == 404
    )
    assert app.client.put(f"/api/messages/{answer_id}/vote", json={"score": 1}).status_code == 404
    assert app.client.delete(f"/api/conversations/{conversation['id']}").status_code == 404


def test_experiments_off_always_use_the_first_components(tmp_path: Path) -> None:
    client, app = start_app(tmp_path, experiments=False)
    with client:
        app.signup()
        pdf = app.upload(CONTRACT)
        for _ in range(5):
            components = app.client.post(f"/api/pdfs/{pdf['id']}/conversations").json()["components"]
            assert components["llm"]["name"] == "anthropic:claude-opus-5-5"
            assert components["retriever"]["name"] == "top_3"
            assert components["memory"]["name"] == "all_history"


def test_the_api_answers_json_404_and_never_the_client(app: App) -> None:
    assert app.client.get("/api/nope").status_code == 404
    assert app.client.get("/api/health").json() == {"status": "ok"}
    assert app.client.get("/api/health").headers["cache-control"] == "no-store"

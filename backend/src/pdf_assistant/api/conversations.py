import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from pydantic_core import PydanticCustomError

from pdf_assistant.ai import AiError
from pdf_assistant.api.deps import CurrentUser, ServicesDep
from pdf_assistant.api.schemas import ComponentScoreOut, ConversationOut, MessageOut, ScoresOut
from pdf_assistant.chat import rag, service
from pdf_assistant.chat.components import KINDS
from pdf_assistant.db import session_scope
from pdf_assistant.documents.service import PdfNotFound
from pdf_assistant.vectors import VectorStoreError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])
MAX_QUESTION_CHARS = 4000


class SendMessage(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise PydanticCustomError("invalid", "Pitanje je prazno.")
        if len(value) > MAX_QUESTION_CHARS:
            raise PydanticCustomError("invalid", f"Pitanje može imati najviše {MAX_QUESTION_CHARS} znakova.")
        return value


class VoteIn(BaseModel):
    score: Literal[1, -1, 0]


def _conversation_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Razgovor ne postoji.")


@router.get("/pdfs/{pdf_id}/conversations")
def list_conversations(pdf_id: str, user: CurrentUser, services: ServicesDep) -> list[ConversationOut]:
    try:
        with session_scope(services.sessions) as db:
            return [ConversationOut.of(c, services.experiment) for c in service.list_conversations(db, user.id, pdf_id)]
    except PdfNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="PDF ne postoji.") from None


@router.post("/pdfs/{pdf_id}/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(pdf_id: str, user: CurrentUser, services: ServicesDep) -> ConversationOut:
    try:
        with session_scope(services.sessions) as db:
            conversation = service.create_conversation(db, user.id, pdf_id, services.experiment)
            return ConversationOut.of(conversation, services.experiment)
    except PdfNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="PDF ne postoji.") from None


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: CurrentUser, services: ServicesDep) -> None:
    try:
        with session_scope(services.sessions) as db:
            service.delete_conversation(db, user.id, conversation_id)
    except service.ConversationNotFound:
        raise _conversation_not_found() from None


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str, body: SendMessage, user: CurrentUser, services: ServicesDep
) -> StreamingResponse:
    """Answer as newline-delimited JSON events:

    {"type": "start", "user_message": Message}
    {"type": "delta", "text": "..."}            repeated
    {"type": "end", "message": Message}          the saved answer with its sources
    {"type": "error", "detail": "..."}          instead of "end"; nothing is saved
    """
    question = body.content

    def start() -> tuple[service.Turn, MessageOut]:
        with session_scope(services.sessions) as db:
            turn = service.start_turn(db, user.id, conversation_id, question)
            return turn, MessageOut.of(turn.user_message)

    try:
        turn, user_message = await asyncio.to_thread(start)
    except service.ConversationNotFound:
        raise _conversation_not_found() from None
    except service.PdfNotReady:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="PDF još nije spreman za razgovor.") from None

    settings = services.settings
    experiment = services.experiment
    llm = services.chat_models[experiment.resolve("llm", turn.llm).name]
    top_k = experiment.top_k(turn.retriever)
    history = rag.recent_history(turn.history, experiment.memory_turns(turn.memory))

    trace = services.tracer.start(
        "chat-turn",
        user_id=user.id,
        session_id=conversation_id,
        input=question,
        metadata={"pdf_id": turn.pdf_id, "llm": turn.llm, "retriever": turn.retriever, "memory": turn.memory},
    )
    outcome: dict[str, str] = {}

    async def traced() -> AsyncIterator[str]:
        try:
            async for line in answer():
                yield line
        finally:
            # Also runs when the browser goes away mid-answer (the generator is closed).
            if "answer" in outcome:
                trace.end(output=outcome["answer"])
            else:
                trace.end(error=outcome.get("error", "the client stopped reading before the end"))

    async def answer() -> AsyncIterator[str]:
        yield _event(type="start", user_message=user_message.model_dump(mode="json"), title=turn.title)

        search_query = question
        if history and settings.rewrite_followups:
            rewrite = trace.child("rewrite-followup", as_type="generation", model=llm.name, input=question)
            try:
                search_query = await rag.standalone_question(question, history, llm)
                rewrite.end(output=search_query)
            except AiError as exc:
                # Searching with the raw follow-up is worse, not broken.
                logger.warning("follow-up rewrite failed, searching with the question as asked: %s", exc)
                rewrite.end(error=str(exc))

        retrieval = trace.child("retrieve", as_type="retriever", input=search_query, metadata={"top_k": top_k})
        try:
            vector = await asyncio.to_thread(services.embedder.embed_query, search_query)
            hits = await asyncio.to_thread(services.store.search, turn.pdf_id, vector, top_k)
        except (AiError, VectorStoreError) as exc:
            logger.warning("retrieval failed: %s", exc)
            retrieval.end(error=str(exc))
            outcome["error"] = str(exc)
            yield _event(type="error", detail="Pretraga dokumenta trenutno ne radi. Pokušaj ponovo.")
            return
        retrieval.end(output=[{"page": h.page, "score": round(h.score, 4)} for h in hits])

        prompt = rag.build_prompt(question, hits, history, max_prompt_tokens=settings.max_prompt_tokens)
        generation = trace.child(
            "answer",
            as_type="generation",
            model=llm.name,
            input=[{"role": "system", "content": prompt.system}, *prompt.messages],
        )
        parts: list[str] = []
        answer_stream = llm.stream(system=prompt.system, messages=prompt.messages)
        try:
            async for piece in answer_stream:
                parts.append(piece)
                yield _event(type="delta", text=piece)
        except AiError as exc:
            logger.warning("generation failed: %s", exc)
            generation.end(error=str(exc))
            outcome["error"] = str(exc)
            yield _event(type="error", detail="Model trenutno ne može da odgovori. Pokušaj ponovo.")
            return
        finally:
            await answer_stream.aclose()  # type: ignore[attr-defined]

        text = "".join(parts).strip()
        generation.end(output=text)
        sources = rag.cited_sources(prompt.used, text)

        def save() -> MessageOut:
            with session_scope(services.sessions) as db:
                return MessageOut.of(service.save_answer(db, conversation_id, text, sources))

        message = await asyncio.to_thread(save)
        outcome["answer"] = text
        yield _event(type="end", message=message.model_dump(mode="json"))

    return StreamingResponse(
        traced(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )


def _event(**fields: object) -> str:
    return json.dumps(fields, ensure_ascii=False) + "\n"


@router.put("/messages/{message_id}/vote")
def vote(message_id: str, body: VoteIn, user: CurrentUser, services: ServicesDep) -> MessageOut:
    try:
        with session_scope(services.sessions) as db:
            return MessageOut.of(service.vote(db, user.id, message_id, body.score))
    except service.MessageNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Poruka ne postoji.") from None
    except service.NotAnAnswer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ocenjuju se samo odgovori.") from None


@router.get("/scores")
def scores(user: CurrentUser, services: ServicesDep) -> ScoresOut:
    experiment = services.experiment
    with session_scope(services.sessions) as db:
        all_tallies = service.tallies(db)
    result: dict[str, list[ComponentScoreOut]] = {}
    for kind in KINDS:
        tallies = all_tallies[kind]
        weights = experiment.weights(kind, tallies)
        names = [c.name for c in experiment.components(kind)]
        names += sorted(n for n in tallies if n not in weights)  # voted on, no longer configured
        rows = []
        for name in names:
            component = experiment.describe(kind, name)
            tally = tallies.get(name)
            rows.append(
                ComponentScoreOut(
                    name=name,
                    label=component.label,
                    active=component.active,
                    up=tally.up if tally else 0,
                    down=tally.down if tally else 0,
                    satisfaction=round(tally.satisfaction, 4) if tally and tally.satisfaction is not None else None,
                    weight=round(weights.get(name, 0.0), 4),
                )
            )
        result[kind] = rows
    return ScoresOut.model_validate(result)

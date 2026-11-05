"""Conversation, message and vote rows. Scoped to the owner like documents.service."""

import itertools
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from pdf_assistant.ai import ChatMessage
from pdf_assistant.chat.components import KINDS, Experiment, Kind, Tally
from pdf_assistant.db import utcnow
from pdf_assistant.documents.service import get_pdf
from pdf_assistant.models import Conversation, Message, PdfStatus, Role, Vote

TITLE_CHARS = 60
NEW_TITLE = "Novi razgovor"


class ConversationNotFound(Exception):
    pass


class MessageNotFound(Exception):
    pass


class PdfNotReady(Exception):
    pass


class NotAnAnswer(Exception):
    pass


def title(conversation: Conversation) -> str:
    for message in conversation.messages:
        if message.role == Role.USER:
            text = " ".join(message.content.split())
            return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1].rstrip() + "…"
    return NEW_TITLE


def _with_messages() -> Any:
    return selectinload(Conversation.messages).selectinload(Message.vote)


def answered_history(messages: list[Message]) -> list[ChatMessage]:
    """Question/answer pairs only. A question whose answer failed or was cut off is left
    out, so the history alternates user/assistant as the model APIs expect."""
    history: list[ChatMessage] = []
    for current, following in itertools.pairwise(messages):
        if current.role == Role.USER and following.role == Role.ASSISTANT:
            history.append({"role": "user", "content": current.content})
            history.append({"role": "assistant", "content": following.content})
    return history


def list_conversations(db: Session, user_id: str, pdf_id: str) -> list[Conversation]:
    get_pdf(db, user_id, pdf_id)
    query = (
        select(Conversation)
        .where(Conversation.pdf_id == pdf_id, Conversation.user_id == user_id)
        .options(_with_messages())
        .order_by(Conversation.created_at.desc())
    )
    return list(db.scalars(query))


def get_conversation(db: Session, user_id: str, conversation_id: str) -> Conversation:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id).options(_with_messages()))
    if conversation is None or conversation.user_id != user_id:
        raise ConversationNotFound(conversation_id)
    return conversation


def create_conversation(db: Session, user_id: str, pdf_id: str, experiment: Experiment) -> Conversation:
    get_pdf(db, user_id, pdf_id)
    all_tallies = tallies(db)
    picked = {kind: experiment.pick(kind, all_tallies[kind]).name for kind in KINDS}
    conversation = Conversation(
        pdf_id=pdf_id, user_id=user_id, llm=picked["llm"], retriever=picked["retriever"], memory=picked["memory"]
    )
    db.add(conversation)
    db.flush()
    conversation.messages = []
    return conversation


def delete_conversation(db: Session, user_id: str, conversation_id: str) -> None:
    db.delete(get_conversation(db, user_id, conversation_id))


@dataclass(frozen=True)
class Turn:
    conversation_id: str
    title: str  # the conversation's title once this question is in
    pdf_id: str
    llm: str
    retriever: str
    memory: str
    history: list[ChatMessage]  # earlier answered questions, oldest first
    user_message: Message


def start_turn(db: Session, user_id: str, conversation_id: str, question: str) -> Turn:
    """Save the question; return what answering it needs."""
    conversation = get_conversation(db, user_id, conversation_id)
    if conversation.pdf.status != PdfStatus.READY:
        raise PdfNotReady(conversation.pdf.status)
    history = answered_history(conversation.messages)
    message = Message(conversation_id=conversation.id, role=Role.USER, content=question, sources=[])
    conversation.messages.append(message)
    db.flush()
    return Turn(
        conversation_id=conversation.id,
        title=title(conversation),
        pdf_id=conversation.pdf_id,
        llm=conversation.llm,
        retriever=conversation.retriever,
        memory=conversation.memory,
        history=history,
        user_message=message,
    )


def save_answer(db: Session, conversation_id: str, answer: str, sources: list[dict[str, Any]]) -> Message:
    message = Message(conversation_id=conversation_id, role=Role.ASSISTANT, content=answer, sources=sources)
    db.add(message)
    db.flush()
    return message


def vote(db: Session, user_id: str, message_id: str, score: int) -> Message:
    """Set (+1 / -1) or clear (0) the vote on an answer."""
    message = db.scalar(select(Message).where(Message.id == message_id).options(selectinload(Message.vote)))
    if message is None or message.conversation.user_id != user_id:
        raise MessageNotFound(message_id)
    if message.role != Role.ASSISTANT:
        raise NotAnAnswer(message_id)
    conversation = message.conversation
    if score == 0:
        if message.vote is not None:
            db.delete(message.vote)
            message.vote = None
    elif message.vote is None:
        message.vote = Vote(
            message_id=message.id,
            llm=conversation.llm,
            retriever=conversation.retriever,
            memory=conversation.memory,
            score=score,
        )
        db.add(message.vote)
    else:
        message.vote.score = score
        message.vote.updated_at = utcnow()
    db.flush()
    return message


def tallies(db: Session) -> dict[Kind, dict[str, Tally]]:
    """Up and down votes per component, across all users."""
    result: dict[Kind, dict[str, Tally]] = defaultdict(dict)
    up = func.sum(case((Vote.score > 0, 1), else_=0))
    down = func.sum(case((Vote.score < 0, 1), else_=0))
    for kind in KINDS:
        column = getattr(Vote, kind)
        for name, ups, downs in db.execute(select(column, up, down).group_by(column)):
            result[kind][name] = Tally(up=int(ups or 0), down=int(downs or 0))
    return {kind: result[kind] for kind in KINDS}

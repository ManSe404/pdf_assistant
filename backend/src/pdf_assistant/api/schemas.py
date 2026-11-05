"""Response bodies. The client's types mirror these (client/src/lib/api)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from pdf_assistant.chat.components import Experiment
from pdf_assistant.chat.service import title
from pdf_assistant.models import Conversation, Message, Pdf, User


class UserOut(BaseModel):
    id: str
    email: str

    @classmethod
    def of(cls, user: User) -> UserOut:
        return cls(id=user.id, email=user.email)


class PdfOut(BaseModel):
    id: str
    name: str
    status: Literal["processing", "ready", "failed"]
    error: str | None
    pages: int | None
    chunks: int | None
    size_bytes: int
    created_at: datetime

    @classmethod
    def of(cls, pdf: Pdf) -> PdfOut:
        return cls(
            id=pdf.id,
            name=pdf.name,
            status=pdf.status.value,
            error=pdf.error,
            pages=pdf.pages,
            chunks=pdf.chunks,
            size_bytes=pdf.size_bytes,
            created_at=pdf.created_at,
        )


class SourceOut(BaseModel):
    n: int
    page: int
    text: str


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    sources: list[SourceOut]
    vote: Literal[1, -1] | None

    @classmethod
    def of(cls, message: Message) -> MessageOut:
        vote = message.vote.score if message.vote is not None else None
        return cls(
            id=message.id,
            role=message.role.value,
            content=message.content,
            created_at=message.created_at,
            sources=[SourceOut.model_validate(s) for s in message.sources or []],
            vote=vote,
        )


class ComponentOut(BaseModel):
    name: str
    label: str


class ComponentsOut(BaseModel):
    llm: ComponentOut
    retriever: ComponentOut
    memory: ComponentOut


class ConversationOut(BaseModel):
    id: str
    pdf_id: str
    title: str
    created_at: datetime
    components: ComponentsOut
    messages: list[MessageOut]

    @classmethod
    def of(cls, conversation: Conversation, experiment: Experiment) -> ConversationOut:
        def component(kind: Literal["llm", "retriever", "memory"], name: str) -> ComponentOut:
            described = experiment.describe(kind, name)
            return ComponentOut(name=described.name, label=described.label)

        return cls(
            id=conversation.id,
            pdf_id=conversation.pdf_id,
            title=title(conversation),
            created_at=conversation.created_at,
            components=ComponentsOut(
                llm=component("llm", conversation.llm),
                retriever=component("retriever", conversation.retriever),
                memory=component("memory", conversation.memory),
            ),
            messages=[MessageOut.of(m) for m in conversation.messages],
        )


class ComponentScoreOut(BaseModel):
    name: str
    label: str
    active: bool
    up: int
    down: int
    satisfaction: float | None
    weight: float


class ScoresOut(BaseModel):
    llm: list[ComponentScoreOut]
    retriever: list[ComponentScoreOut]
    memory: list[ComponentScoreOut]

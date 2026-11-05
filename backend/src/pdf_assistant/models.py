"""Tables. Ids are random UUID strings so URLs don't reveal how many rows exist."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pdf_assistant.db import Base, UTCDateTime, utcnow


def new_id() -> str:
    return str(uuid.uuid4())


def _enum(cls: type[StrEnum]) -> Enum:
    """Stored as its value in a plain string column; loaded back as the enum member."""
    return Enum(cls, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


class PdfStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Pdf(Base):
    __tablename__ = "pdfs"
    __table_args__ = (Index("ix_pdfs_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[PdfStatus] = mapped_column(_enum(PdfStatus), default=PdfStatus.PROCESSING)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    pages: Mapped[int | None] = mapped_column(Integer, default=None)
    chunks: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="pdf", cascade="all, delete-orphan", passive_deletes=True
    )


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_pdf_created", "pdf_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pdf_id: Mapped[str] = mapped_column(ForeignKey("pdfs.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # The experiment components picked when the conversation started (chat.components).
    llm: Mapped[str] = mapped_column(String(200))
    retriever: Mapped[str] = mapped_column(String(50))
    memory: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    pdf: Mapped[Pdf] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        order_by="Message.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[Role] = mapped_column(_enum(Role))
    content: Mapped[str] = mapped_column(Text)
    # [{"n": 1, "page": 3, "text": "..."}] for answers; the sources the prompt carried.
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    vote: Mapped[Vote | None] = relationship(back_populates="message", uselist=False)


class Vote(Base):
    """A thumbs up (+1) or down (-1) on one answer.

    The components are copied from the conversation so the experiment keeps its votes
    when the conversation or the PDF is deleted (the message link is then cleared).
    """

    __tablename__ = "votes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), unique=True, default=None
    )
    llm: Mapped[str] = mapped_column(String(200))
    retriever: Mapped[str] = mapped_column(String(50))
    memory: Mapped[str] = mapped_column(String(50))
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    message: Mapped[Message | None] = relationship(back_populates="vote")

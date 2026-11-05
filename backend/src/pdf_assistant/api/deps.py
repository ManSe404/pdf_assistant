"""What every request can depend on: the shared services and the signed-in user."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from pdf_assistant import auth
from pdf_assistant.ai import ChatModel, Embedder
from pdf_assistant.chat.components import Experiment
from pdf_assistant.db import session_scope
from pdf_assistant.documents.indexing import IndexQueue
from pdf_assistant.documents.storage import PdfStorage
from pdf_assistant.models import User
from pdf_assistant.settings import Settings
from pdf_assistant.tracing import Tracer
from pdf_assistant.vectors import VectorStore


@dataclass
class Services:
    settings: Settings
    sessions: sessionmaker[Session]
    storage: PdfStorage
    chat_models: dict[str, ChatModel]
    embedder: Embedder
    store: VectorStore
    tracer: Tracer
    experiment: Experiment
    queue: IndexQueue


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


def optional_user(request: Request, services: ServicesDep) -> User | None:
    token = request.cookies.get(auth.COOKIE)
    if not token:
        return None
    user_id = auth.user_id_from_token(token, secret=services.settings.secret_key.get_secret_value())
    if user_id is None:
        return None
    with session_scope(services.sessions) as db:
        return db.get(User, user_id)


def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Prijavi se.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]

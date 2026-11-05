import re

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from pdf_assistant import auth
from pdf_assistant.api.deps import OptionalUser, ServicesDep
from pdf_assistant.api.schemas import UserOut
from pdf_assistant.db import session_scope

router = APIRouter(prefix="/auth", tags=["auth"])


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if not _EMAIL.match(value):
            raise PydanticCustomError("invalid", "Adresa e-pošte nije ispravna.")
        return value

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if len(value) < 8:
            raise PydanticCustomError("invalid", "Lozinka mora imati bar 8 znakova.")
        # bcrypt only reads 72 bytes and bcrypt 5 refuses longer input.
        if len(value.encode()) > 72:
            raise PydanticCustomError("invalid", "Lozinka može imati najviše 72 bajta (oko 72 slova bez dijakritika).")
        return value


def _set_session(response: Response, user_id: str, services: ServicesDep) -> None:
    settings = services.settings
    token = auth.issue_token(user_id, secret=settings.secret_key.get_secret_value(), days=settings.session_days)
    response.set_cookie(
        auth.COOKIE,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api",
    )


@router.get("/user")
def get_user(user: OptionalUser) -> UserOut | None:
    return UserOut.of(user) if user else None


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: Credentials, response: Response, services: ServicesDep) -> UserOut:
    if not services.settings.allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Registracija je zatvorena.")
    try:
        with session_scope(services.sessions) as db:
            user = auth.register(db, email=body.email, password=body.password)
            out = UserOut.of(user)
    except auth.EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Nalog sa ovom adresom već postoji.") from None
    _set_session(response, out.id, services)
    return out


@router.post("/signin")
def signin(body: Credentials, response: Response, services: ServicesDep) -> UserOut:
    try:
        with session_scope(services.sessions) as db:
            out = UserOut.of(auth.authenticate(db, email=body.email, password=body.password))
    except auth.InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Pogrešna adresa ili lozinka.") from None
    _set_session(response, out.id, services)
    return out


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
def signout(response: Response) -> None:
    response.delete_cookie(auth.COOKIE, path="/api")

"""Accounts: bcrypt password hashes and a signed session token (JWT) that the API keeps
in an httpOnly cookie, so page scripts never see it."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pdf_assistant.models import User

ALGORITHM = "HS256"
COOKIE = "pdfa_session"


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# Compared against when the email is unknown, so a wrong email costs as much time as a
# wrong password and response times don't reveal which accounts exist.
_DUMMY_HASH = hash_password("not-a-real-password")


def register(db: Session, *, email: str, password: str) -> User:
    email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailTaken(email)
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, *, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise InvalidCredentials
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials
    return user


def issue_token(user_id: str, *, secret: str, days: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + timedelta(days=days)}, secret, algorithm=ALGORITHM)


def user_id_from_token(token: str, *, secret: str) -> str | None:
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None

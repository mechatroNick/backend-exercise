"""Small persistence adapter for canonical user lookups and inserts."""

from __future__ import annotations

from sqlmodel import Session, select

from app.auth.models import User


class UserRepository:
    """Expose only the user operations required by the authentication service."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> None:
        """Stage a new user in the caller-owned transaction."""
        self._session.add(user)

    def find_by_canonical_email(self, canonical_email: str) -> User | None:
        """Return the sole user matching an already canonical email, if present."""
        statement = select(User).where(User.email == canonical_email)
        return self._session.exec(statement).one_or_none()

    def find_by_id(self, user_id: int) -> User | None:
        """Return a user by its durable identifier, if present."""
        statement = select(User).where(User.id == user_id)
        return self._session.exec(statement).one_or_none()


__all__ = ["UserRepository"]

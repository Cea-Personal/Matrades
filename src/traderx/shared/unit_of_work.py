from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker


class UnitOfWork(Protocol):
    session: Session

    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self._session_factory()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


@contextmanager
def locked_rows(session: Session, *statements: object) -> Iterator[None]:
    """Execute lock queries in a caller-defined deterministic order."""
    for statement in statements:
        session.execute(statement)  # type: ignore[arg-type]
    yield

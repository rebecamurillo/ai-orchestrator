"""The session factory the unit of work opens sessions from.

`expire_on_commit=False` because a use case commonly commits and then returns the entity it
just wrote; with expiry on, every attribute read after the commit would issue a fresh
`SELECT` against a connection the unit of work is about to release.
"""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build the process-wide session factory bound to `engine`."""
    return sessionmaker(bind=engine, expire_on_commit=False)

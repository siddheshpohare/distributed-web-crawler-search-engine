"""
db/session.py — Database Engine & Session Factory (Phase 2)

Creates the SQLAlchemy engine from the DATABASE_URL environment variable
and provides a session factory (SessionLocal) for use in route handlers.

Usage in a route handler (dependency injection pattern):

    from api.db.session import get_db
    from fastapi import Depends
    from sqlalchemy.orm import Session

    @router.get("/example")
    def example(db: Session = Depends(get_db)):
        ...

The get_db() generator opens a session, yields it to the handler,
then closes it — even if the handler raises an exception.

Environment variable:
    DATABASE_URL  e.g. postgresql://user:password@localhost:5432/crawlerdb
                  Falls back to a local default for development.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ── Engine ────────────────────────────────────────────────────────────────────

# Read connection string from the environment.
# For local development: export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/crawlerdb"
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/crawlerdb",
)

engine = create_engine(
    DATABASE_URL,
    # Echo SQL statements to stdout in debug/dev mode.
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    # Pool settings: keep up to 5 connections open, allow 10 overflow.
    pool_size=5,
    max_overflow=10,
)

# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,   # We manage commits explicitly.
    autoflush=False,    # Flush only on commit or explicit session.flush().
)


# ── Base class for ORM models ─────────────────────────────────────────────────

class Base(DeclarativeBase):
    """All ORM models inherit from this base."""
    pass


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db():
    """
    FastAPI dependency that provides a database session per request.

    Opens a session at the start of the request and closes it after
    the response is sent — even if an exception occurs.

    Yields
    ------
    sqlalchemy.orm.Session
        An active database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

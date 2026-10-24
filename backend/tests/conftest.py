"""Pytest fixtures for isolated database testing."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


# Ensure SQLite enforces Foreign Key constraints for test isolation
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(scope="session")
def engine():
    """Create a single shared test engine."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    return test_engine


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Provide a pristine, isolated database session per test.

    Recreates all schema tables and cleanly tears them down.
    """
    connection = engine.connect()
    transaction = connection.begin()
    Base.metadata.create_all(bind=connection)

    Session = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    session = Session()

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    Base.metadata.drop_all(bind=connection)
    connection.close()


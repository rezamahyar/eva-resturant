"""Shared pytest fixtures for EVA Restaurant.

pytest.ini / pyproject.toml sets pythonpath = ["."] so the package is
importable without manual sys.path hacks.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eva_restaurant.core import Base


@pytest.fixture
def memory_session():
    """Isolated in-memory SQLite session for unit tests (no disk side-effects)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

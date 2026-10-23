"""Neo4j driver singleton — one driver per process, shared across requests."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from neo4j import GraphDatabase, Driver

_driver: Driver | None = None


def get_driver() -> Driver:
    """Return the module-level driver, creating it on first call."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
    return _driver


def get_database() -> str | None:
    """Return the configured database name."""
    return os.environ.get("NEO4J_DATABASE")


def get_session():
    """Return a new Neo4j session using the singleton driver and configured database."""
    db = get_database()
    if db:
        return get_driver().session(database=db)
    return get_driver().session()


def close_driver() -> None:
    """Shut down the driver cleanly."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

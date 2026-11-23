import sqlite3
from collections.abc import Generator
from contextlib import closing
from pathlib import Path

import pytest

from litecrate import Database


@pytest.fixture
def db() -> Generator[Database]:
    with closing(Database(":memory:")) as database:
        yield database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "database.sqlite"


@pytest.fixture
def file_db(db_path: Path) -> Generator[Database]:
    with closing(Database(db_path)) as database:
        yield database


@pytest.fixture
def sqlite_db(db_path: Path) -> Generator[sqlite3.Connection]:
    with closing(sqlite3.connect(db_path, isolation_level=None)) as connection:
        yield connection


@pytest.fixture
def items(db: Database) -> Database:
    with db:
        db.create_table("items", ("p", "id", int), (0, "label", str), flexible=True)
        db.insert("items", id=1, label="one", score=8, tags=["old"])
        db.insert("items", id=2, label="two", score=20)
        db.insert("items", id=3, label="three")

    return db

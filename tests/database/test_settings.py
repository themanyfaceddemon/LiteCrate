import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from litecrate import Database


def test_journal_mode_and_auto_vacuum_persist(tmp_path: Path):
    path = tmp_path / "pragmas.sqlite"
    with closing(Database(path)) as database:
        database.set_journal_mode("WAL")
        database.set_auto_vacuum("FULL")
        database.vacuum()

    with closing(sqlite3.connect(path)) as raw:
        assert raw.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert raw.execute("PRAGMA auto_vacuum").fetchone() == (1,)


def test_unknown_auto_vacuum_mode_is_rejected(db: Database):
    with pytest.raises(ValueError):
        db.set_auto_vacuum("invalid")  # pyright: ignore[reportArgumentType]


def test_unknown_journal_mode_is_rejected(db: Database):
    with pytest.raises(ValueError):
        db.set_journal_mode("invalid")  # pyright: ignore[reportArgumentType]


def test_wal_is_unavailable_for_an_in_memory_database(db: Database):
    with pytest.raises(RuntimeError):
        db.set_journal_mode("WAL")


def test_incremental_vacuum_frees_pages(file_db: Database, sqlite_db: sqlite3.Connection):
    file_db.set_auto_vacuum("INCREMENTAL")
    file_db.vacuum()
    file_db.create_table("payloads", ("p", "id", int), (0, "payload", bytes))

    with file_db:
        for _ in range(20):
            file_db.insert("payloads", payload=b"x" * 4096)

    file_db.delete_all("payloads")
    before = sqlite_db.execute("PRAGMA freelist_count").fetchone()[0]
    assert before > 2

    file_db.incremental_vacuum(2)
    after_limit = sqlite_db.execute("PRAGMA freelist_count").fetchone()[0]
    assert before - 2 <= after_limit < before

    file_db.incremental_vacuum()
    assert sqlite_db.execute("PRAGMA freelist_count").fetchone() == (0,)


@pytest.mark.parametrize(
    "pages",
    [0, -1, True, 1.5, "10"],
)
def test_incremental_vacuum_invalid_pages(db: Database, pages):
    with pytest.raises(ValueError, match="Pages"):
        db.incremental_vacuum(pages)

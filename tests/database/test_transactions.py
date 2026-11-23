import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from litecrate import Database
from litecrate.utils import get_index_identifier


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_table", ("new", ("i", "name", str))),
        ("rename_table", ("old", "new")),
    ],
)
def test_index_conflict_rolls_back_only_the_failed_schema_change(
    file_db: Database,
    sqlite_db: sqlite3.Connection,
    method: str,
    args: tuple[object, ...],
):
    file_db.create_table("external", (0, "name", str))
    file_db.create_table("old", ("i", "name", str))
    original_indexes = file_db.get_table_indexes("old")
    index_name = get_index_identifier("new", "name")
    sqlite_db.execute(f"CREATE INDEX {index_name} ON external (name)")

    with file_db:
        with pytest.raises(sqlite3.OperationalError, match="already exists"):
            getattr(file_db, method)(*args)
        file_db.insert("old", name="saved")

    assert file_db.get_tables() == ["external", "old"]
    assert file_db.get_table_indexes("old") == original_indexes
    assert file_db.select("old") == [{"name": "saved"}]


def test_batch_is_visible_to_other_connections_only_after_commit(tmp_path: Path):
    path = tmp_path / "batch.sqlite"
    with closing(Database(path)) as writer:
        writer.create_table("events", ("p", "id", int))
        with closing(Database(path)) as reader:
            with writer as batch:
                assert batch is writer
                writer.insert("events", id=1)
                writer.insert("events", id=2)
                assert writer.count("events") == 2
                assert reader.count("events") == 0
            assert reader.count("events") == 2


def test_rollback_restores_data_schema_and_metadata(items: Database):
    with pytest.raises(sqlite3.IntegrityError), items:
        items.rename_table("items", "renamed")
        items.delete_table("renamed")
        items.create_table("temporary", ("p", "id", int))
        items.insert("temporary", id=1)
        items.insert("temporary", id=1)

    assert items.get_tables() == ["items"]
    assert items.count("items", "score = ?", 8) == 1
    with items:
        items.insert("items", id=4, label="usable", score=42)

    assert items.select_one("items", "score = 42") == {
        "id": 4,
        "label": "usable",
        "score": 42,
    }


def test_nested_transaction_keeps_outer_transaction_usable(items: Database):
    with items:
        items.update("items", "id = 1", label="outer")
        with pytest.raises(RuntimeError, match="Nested"), items:
            pytest.fail("Nested transaction was accepted")

        items.update("items", "id = 2", label="outer")

    assert items.count("items", "label = 'outer'") == 2


def test_sqlite_initiated_rollback_preserves_original_exception(
    file_db: Database, sqlite_db: sqlite3.Connection
):
    file_db.create_table("items", ("p", "id", int), (0, "label", str), flexible=True)
    file_db.insert("items", id=1, label="one", score=8)
    sqlite_db.execute(
        "CREATE TRIGGER reject_reserved_id BEFORE INSERT ON items "
        "WHEN NEW.id = 1 BEGIN SELECT RAISE(ROLLBACK, 'reserved id'); END"
    )

    with pytest.raises(sqlite3.IntegrityError, match="reserved id") as caught, file_db:
        file_db.rename_table("items", "pending")
        file_db.insert("pending", id=1)

    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_TRIGGER
    assert file_db.get_tables() == ["items"]
    with file_db:
        assert file_db.update("items", "score = 8", label="restored") == 1

    assert file_db.select_one("items", "id = 1") == {
        "id": 1,
        "label": "restored",
        "score": 8,
    }


def test_table_creation_can_be_retried_after_a_busy_error(
    db_path: Path, sqlite_db: sqlite3.Connection
):
    with closing(Database(db_path, timeout=0)) as writer:
        writer.set_journal_mode("DELETE")
        writer.create_table("events", ("p", "id", int))
        with sqlite_db:
            sqlite_db.execute("BEGIN")
            assert sqlite_db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
            with pytest.raises(sqlite3.OperationalError) as caught:
                writer.create_table("pending", (0, "value", int))
            assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY

        assert writer.get_tables() == ["events"]
        with writer:
            writer.create_table("pending", (0, "value", int))
            writer.insert("pending", value=1)
        assert writer.select("pending") == [{"value": 1}]


def test_failed_commit_rolls_back_and_allows_the_next_transaction(
    db_path: Path, sqlite_db: sqlite3.Connection
):
    with closing(Database(db_path, timeout=0)) as writer:
        writer.set_journal_mode("DELETE")
        writer.create_table("events", ("p", "id", int))
        with sqlite_db:
            sqlite_db.execute("BEGIN")
            assert sqlite_db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
            body_finished = False
            with pytest.raises(sqlite3.OperationalError) as caught, writer:
                writer.create_table("pending", (0, "value", int))
                writer.insert("events", id=1)
                body_finished = True

            assert body_finished
            assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY

        assert writer.get_tables() == ["events"]
        assert writer.count("events") == 0
        with writer:
            writer.insert("events", id=2)

        assert writer.select("events") == [{"id": 2}]


def test_rollback_restores_column_types_for_reads_and_writes(db: Database):
    db.create_table("docs", ("p", "id", int), (0, "config", dict))
    db.insert("docs", ID=1, config={"old": True})

    with pytest.raises(RuntimeError, match="rollback"), db:
        db.delete_table("docs")
        db.create_table("docs", ("p", "id", int), (0, "config", str))
        db.insert("docs", ID=2, config="new")
        assert db.select_one("docs") == {"id": 2, "config": "new"}
        raise RuntimeError("rollback")

    assert db.insert("docs", ID=2, config={"new": True}) == 2
    assert db.update("docs", "id = ?1", 1, config={"saved": True}) == 1
    assert db.select("docs") == [
        {"id": 1, "config": {"saved": True}},
        {"id": 2, "config": {"new": True}},
    ]

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from litecrate import Database


def test_tables_are_listed_by_normalized_name(db: Database):
    assert db.get_tables() == []
    assert "_litecrate_meta" in db.get_tables(include_internal=True)

    db.create_table("Zoo", ("p", "id", int))
    db.create_table("Accounts", ("u", "login", str))

    assert db.get_tables() == ["accounts", "zoo"]


def test_creating_an_existing_table_preserves_its_rows_and_columns(db: Database):
    db.create_table("Accounts", ("u", "login", str))
    db.insert("ACCOUNTS", login="alice")

    db.create_table("accounts", (0, "other", int))

    assert db.select("accounts") == [{"login": "alice"}]
    db.insert("accounts", login="bob")
    assert db.count("accounts") == 2


def test_dropping_a_table_ignores_case_and_can_be_repeated(db: Database):
    db.create_table("Zoo", ("p", "id", int))
    db.create_table("Accounts", ("u", "login", str))

    db.delete_table("ZOO")
    db.delete_table("zoo")

    assert db.get_tables() == ["accounts"]


@pytest.mark.parametrize(
    "values",
    [{"id": 1, "login": "bob"}, {"id": 2, "login": "alice"}, {"id": 3}],
    ids=["duplicate-primary-key", "duplicate-unique-value", "missing-not-null-value"],
)
def test_insert_enforces_column_constraints(db: Database, values: dict[str, object]):
    db.create_table("users", ("p", "id", int), ("un", "login", str))
    db.insert("users", id=1, login="alice")

    with pytest.raises(sqlite3.IntegrityError):
        db.insert("users", **values)

    assert db.select("users") == [{"id": 1, "login": "alice"}]


@pytest.mark.parametrize(
    "flags",
    ["A", pytest.param(0b10011, id="numeric-mask-for-ain")],
)
def test_autoincrement_survives_deletion_and_reopen(tmp_path: Path, flags: str | int):
    path = tmp_path / "events.sqlite"
    with closing(Database(path)) as db:
        db.create_table("events", (flags, "id", int))
        assert db.get_table_indexes("events") == []
        assert db.insert("events") == 1
        assert db.insert("events", id=10) == 10
        assert db.delete_all("events") == 2

    with closing(Database(path)) as db:
        assert db.insert("events") == 11
        assert db.select("events") == [{"id": 11}]


@pytest.mark.parametrize("colum_type", [None, bool, str, dict])
def test_autoincrement_requires_int(db: Database, colum_type: type | None):
    with pytest.raises(ValueError, match="AUTOINCREMENT.*int"):
        db.create_table("events", ("pa", "id", colum_type))

    assert db.get_tables() == []


@pytest.mark.parametrize(
    ("column", "error"),
    [
        ((0, "_DaTa", str), ValueError),
        ((0, "bad\0name", int), ValueError),
        (("z", "field", str), ValueError),
        ((0, "field", set), TypeError),
    ],
)
def test_invalid_column_definition_creates_no_table(db: Database, column, error):
    with pytest.raises(error):
        db.create_table("broken", column)
    assert db.get_tables() == []


@pytest.mark.parametrize("method", ["create_table", "delete_table", "select"])
def test_metadata_table_is_reserved(db: Database, method: str):
    with pytest.raises(ValueError, match="reserved"):
        getattr(db, method)("_LiteCrate_Meta")
    assert "_litecrate_meta" in db.get_tables(include_internal=True)

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from litecrate import Database
from litecrate.utils import sanitize_identifier


def test_index_flag_skips_columns_that_already_have_constraints(
    file_db: Database, sqlite_db: sqlite3.Connection
):
    file_db.create_table(
        "users",
        ("piu", "id", int),
        ("ui", "login", str),
        ("ni", "team", str),
    )
    (index_name,) = file_db.get_table_indexes("users")
    assert sqlite_db.execute(
        "SELECT name FROM pragma_index_info(?)", (index_name,)
    ).fetchall() == [("team",)]


def test_rename_preserves_managed_and_external_indexes(
    file_db: Database, sqlite_db: sqlite3.Connection
):
    file_db.create_table(
        "old", ("p", "id", int), ("i", 'nick"name', str), ("u", "code", str)
    )
    file_db.create_index("old", "code")
    sqlite_db.execute("CREATE INDEX custom_pair ON old (id, code)")

    file_db.rename_table("old", "new")

    indexes = file_db.get_table_indexes("new")
    assert len(indexes) == 3
    assert "custom_pair" in indexes
    for column in ('nick"name', "code"):
        file_db.remove_index("new", column)
    file_db.remove_index("new", "code")
    assert file_db.get_table_indexes("new") == ["custom_pair"]

    file_db.insert("new", code="one")
    with pytest.raises(sqlite3.IntegrityError):
        file_db.insert("new", code="one")


@pytest.mark.parametrize("column", ["lable", "score"])
def test_column_index_requires_a_declared_column(items: Database, column: str):
    with pytest.raises(sqlite3.OperationalError):
        items.create_index("items", column)

    assert items.get_table_indexes("items") == []


def test_column_index_accepts_the_column_name_in_uppercase(
    file_db: Database, sqlite_db: sqlite3.Connection
):
    file_db.create_table("items", (0, "label", str))
    file_db.create_index("items", "LABEL")

    (index_name,) = file_db.get_table_indexes("items")
    assert sqlite_db.execute(
        "SELECT name FROM pragma_index_info(?)", (index_name,)
    ).fetchall() == [("label",)]


def test_index_on_external_generated_column(file_db: Database, sqlite_db: sqlite3.Connection):
    sqlite_db.execute(
        "CREATE TABLE external (name TEXT, folded TEXT GENERATED ALWAYS AS (lower(name)))"
    )
    file_db.create_index("external", "folded")

    (index_name,) = file_db.get_table_indexes("external")
    assert sqlite_db.execute(
        "SELECT name FROM pragma_index_info(?)", (index_name,)
    ).fetchall() == [("folded",)]


def test_flexible_field_index_survives_reopen_and_rename(tmp_path: Path):
    path = tmp_path / "indexed.sqlite"
    field = "score.\"'\\"
    condition = f"{sanitize_identifier(field)} = ?"
    with closing(Database(path)) as db:
        db.create_table('old "docs"', ("p", "id", int), flexible=True)
        db.insert('old "docs"', **{field: 12})
        db.insert('old "docs"', **{field: 24})
        db.create_index('old "docs"', field, flexible=True)

    with closing(Database(path)) as db:
        db.rename_table('old "docs"', "new docs")
        assert len(db.get_table_indexes("new docs")) == 1
        assert db.select_one("new docs", condition, 12) == {"id": 1, field: 12}
        assert db.update("new docs", condition, 12, **{field: 36}) == 1
        assert db.count("new docs", condition, 12) == 0
        assert db.delete("new docs", condition, 36) == 1

        db.remove_index("new docs", field)
        assert db.get_table_indexes("new docs") == []
        assert db.select_one("new docs", condition, 24) == {"id": 2, field: 24}


def test_flexible_index_requires_a_flexible_table(db: Database):
    db.create_table("strict", (0, "name", str))
    with pytest.raises(ValueError):
        db.create_index("strict", "score", flexible=True)
    assert db.get_table_indexes("strict") == []


def test_flexible_index_rejects_a_declared_column(items: Database):
    with pytest.raises(ValueError):
        items.create_index("items", "label", flexible=True)
    assert items.get_table_indexes("items") == []

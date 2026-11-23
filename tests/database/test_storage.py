import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from litecrate import Database


def test_types_and_metadata_survive_rename_and_reopen(tmp_path: Path):
    path = tmp_path / "typed.sqlite"
    settings_key = 'settings,: %"'
    expected = {
        "id": 1,
        settings_key: {"language": "\u03bb"},
        "tags": [False, None],
        "active": True,
        "weight": 0.25,
        "raw": b"\x00\xff",
        "note": "hello",
        "anything": 17,
        "extra.key": {"v": [1, 2]},
    }
    with closing(Database(path)) as writer, writer:
        writer.create_table(
            "Docs",
            ("p", "id", int),
            (0, settings_key, dict),
            (0, "tags", list),
            (0, "active", bool),
            (0, "weight", float),
            (0, "raw", bytes),
            (0, "note", str),
            (0, "anything"),
            flexible=True,
        )
        writer.insert("docs", **expected)
        writer.rename_table("docs", "Saved Docs")

    with closing(Database(path)) as reader:
        assert reader.get_tables() == ["saved docs"]
        row = reader.select_one("SAVED DOCS", "id = ?", 1)
        assert row == expected
        assert row is not None and row["active"] is True
        changes = {settings_key: None, "tags": None, "active": False}
        assert reader.update("saved docs", "id = 1", **changes) == 1
        row = reader.select_one("saved docs", "id = 1")
        assert row is not None
        assert row[settings_key] is None and row["tags"] is None
        assert row["active"] is False


@pytest.mark.parametrize(
    ("settings", "tags", "extra"),
    [
        ("[]", None, None),
        (None, "{}", None),
        (None, None, "[]"),
        (None, None, "invalid JSON"),
    ],
    ids=["object-column", "list-column", "extra-must-be-object", "malformed-extra"],
)
@pytest.mark.parametrize("method", ["select", "select_one"])
def test_read_rejects_invalid_stored_json(
    file_db: Database,
    sqlite_db: sqlite3.Connection,
    settings: str | None,
    tags: str | None,
    extra: str | None,
    method: str,
):
    file_db.create_table("docs", (0, "settings", dict), (0, "tags", list), flexible=True)
    sqlite_db.execute(
        "INSERT INTO docs(settings, tags, _data) VALUES (?, ?, ?)",
        (settings, tags, extra),
    )
    with pytest.raises(ValueError):
        getattr(file_db, method)("docs")


@pytest.mark.parametrize("damaged", ["missing_separator", "field:unknown_type"])
def test_reopen_reports_invalid_metadata(tmp_path: Path, damaged: str):
    path = tmp_path / "metadata.sqlite"
    with closing(Database(path)) as writer:
        writer.create_table("docs", (0, "field", str))

    with closing(sqlite3.connect(path, isolation_level=None)) as raw:
        raw.execute(
            "UPDATE _litecrate_meta SET cache_colums = ? WHERE table_name = 'docs'",
            (damaged,),
        )

    with pytest.raises(ValueError, match="Invalid cache metadata.*docs"):  # noqa: SIM117
        with closing(Database(path)):
            pass


def test_closed_database_rejects_queries():
    db = Database(":memory:")
    db.close()
    with pytest.raises(sqlite3.ProgrammingError):
        db.get_tables()

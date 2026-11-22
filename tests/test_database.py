import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from litecrate.database.db_class import Database
from litecrate.utils.colum_work import ColumBitEnum


@pytest.fixture
def db() -> Iterator[Database]:
    with closing(Database(":memory:")) as database:
        yield database


@pytest.fixture
def items(db: Database) -> Database:
    with db:
        db.create_table("items", ("p", "id", int), (0, "label", str), flexible=True)
        db.insert("items", id=1, label="one", score=8, tags=["old"])
        db.insert("items", id=2, label="two", score=20)
        db.insert("items", id=3, label="three")

    return db


def test_create_list_and_drop_tables(db: Database):
    assert db.get_tables() == []
    assert "_litecrate_meta" in db.get_tables(include_internal=True)

    db.create_table("Zoo", ("p", "id", int))
    db.create_table("Accounts", ("u", "login", str))
    db.insert("ACCOUNTS", login="alice")
    db.create_table("accounts", (0, "other", int))

    assert db.get_tables() == ["accounts", "zoo"]
    assert db.select("accounts") == [{"login": "alice"}]
    db.delete_table("ZOO")
    db.delete_table("zoo")
    assert db.get_tables() == ["accounts"]


def test_default_values_and_no_matches(db: Database):
    db.create_table("events", ("p", "id", int), (0, "note"))
    assert db.select("events") == []
    assert db.select_one("events") is None

    row_id = db.insert("events")
    assert isinstance(row_id, int)
    assert db.select_one("events", "id = ?", row_id) == {"id": row_id, "note": None}
    assert db.count("events", "  ") == 1
    assert db.count("events", "id < 0") == 0
    assert db.update("events", "id < 0", note="unused") == 0
    assert db.delete("events", "id < 0") == 0


def test_crud_affects_only_matching_rows(db: Database):
    db.create_table("users", ("p", "id", int), (0, "team", str))
    for user_id, team in [(1, "red"), (2, "blue"), (3, "red")]:
        assert db.insert("users", id=user_id, team=team) == user_id

    assert {row["id"] for row in db.select("users", "team = ?", "red")} == {1, 3}
    assert db.update("users", "team = ?", "red", team="green") == 2
    assert db.count("users", "team = ?", "green") == 2
    assert db.delete("users", "team = ?", "green") == 2
    assert db.select("users") == [{"id": 2, "team": "blue"}]


def test_primary_unique_and_not_null_constraints(db: Database):
    db.create_table("users", ("p", "id", int), ("un", "login", str))
    db.insert("users", id=1, login="alice")
    for values in ({"id": 1, "login": "bob"}, {"id": 2, "login": "alice"}, {"id": 3}):
        with pytest.raises(sqlite3.IntegrityError):
            db.insert("users", **values)

    assert db.select("users") == [{"id": 1, "login": "alice"}]


def test_explicit_index_flag_is_redundant_on_primary_and_unique_columns(db: Database):
    db.create_table(
        "users",
        ("piu", "id", int),
        (ColumBitEnum.UNIQUE | ColumBitEnum.INDEX, "login", str),
        (ColumBitEnum.NOT_NULL | ColumBitEnum.INDEX, "team", str),
    )
    (index_name,) = db.get_table_indexes("users")
    assert db._conn.execute(
        "SELECT name FROM pragma_index_info(?)", (index_name,)
    ).fetchall() == [("team",)]


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


def test_strict_table_rejects_unknown_columns(db: Database):
    db.create_table("users", (0, "login", str))
    with pytest.raises(KeyError, match="extra"):
        db.insert("users", login="alice", extra=True)
    db.insert("users", login="bob")
    with pytest.raises(KeyError, match="extra"):
        db.update("users", "1", login="changed", extra=True)
    assert db.select("users") == [{"login": "bob"}]


@pytest.mark.parametrize(
    ("values", "error"),
    [
        ({"settings": []}, TypeError),
        ({"tags": {}}, TypeError),
        ({"score": float("nan")}, ValueError),
        ({"extra": b"bytes"}, TypeError),
        ({"_DATA": "{}"}, ValueError),
        ({"name": "one", "NAME": "two"}, ValueError),
        ({"extra": 1, "EXTRA": 2}, ValueError),
    ],
)
def test_invalid_values_do_not_write_partial_rows(db: Database, values, error):
    db.create_table(
        "docs",
        (0, "name", str),
        (0, "settings", dict),
        (0, "tags", list),
        flexible=True,
    )
    with pytest.raises(error):
        db.insert("docs", **values)
    assert db.count("docs") == 0


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
        assert row["active"] is True  # pyright: ignore[reportOptionalSubscript]
        changes = {settings_key: None, "tags": None, "active": False}
        assert reader.update("saved docs", "id = 1", **changes) == 1
        row = reader.select_one("saved docs", "id = 1")
        assert row[settings_key] is None and row["tags"] is None  # pyright: ignore[reportOptionalSubscript]
        assert row["active"] is False  # pyright: ignore[reportOptionalSubscript]


def test_flexible_update_replaces_nested_value_and_preserves_siblings(items: Database):
    items.update("items", "id = 1", config={"old": 1, "drop": True}, extra=None)
    changed = items.update(
        "items",
        "score = ?",
        8,
        label="changed",
        config={"new": [2]},
        extra=False,
        nullable=None,
    )
    assert changed == 1
    row = items.select_one("items", "id = 1")
    assert row == {
        "id": 1,
        "label": "changed",
        "score": 8,
        "tags": ["old"],
        "config": {"new": [2]},
        "extra": False,
        "nullable": None,
    }
    assert row["extra"] is False  # pyright: ignore[reportOptionalSubscript]
    assert items.delete("items", "score = ?", 20) == 1
    assert items.select_one("items", "id = 3") == {"id": 3, "label": "three"}


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
def test_read_rejects_invalid_stored_json(db: Database, settings, tags, extra):
    db.create_table("docs", (0, "settings", dict), (0, "tags", list), flexible=True)
    db._conn.execute(
        "INSERT INTO docs(settings, tags, _data) VALUES (?, ?, ?)",
        (settings, tags, extra),
    )
    with pytest.raises(ValueError):
        db.select_one("docs")


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


@pytest.mark.parametrize(
    ("key", "identifier"),
    [
        ('a"b', '"a""b"'),
        (r"a\b", r'"a\b"'),
        ("a'b", '"a\'b"'),
        ("key.at[0]", '"key.at[0]"'),
        ("line\nbreak", '"line\nbreak"'),
        ("select", '"select"'),
        ("", '""'),
    ],
)
def test_flexible_key_is_one_literal_name(db: Database, key: str, identifier: str):
    db.create_table("docs", ("p", "id", int), flexible=True)
    db.insert("docs", id=1, **{key: "before"})
    db.insert("docs", id=2)
    assert db.count("docs", f"{identifier} = ?", "before") == 1
    assert db.update("docs", f"{identifier} = ?", "before", **{key: "after"}) == 1
    assert db.update("docs", "id = ?", 2, **{key: [1, None]}) == 1
    assert db.select_one("docs", f"{identifier} = ?", "after") == {
        "id": 1,
        key: "after",
    }
    assert db.select_one("docs", "id = 2") == {"id": 2, key: [1, None]}


@pytest.mark.parametrize(
    ("condition", "args", "ids"),
    [
        ("score BETWEEN ? AND ? AND label LIKE ?", (5, 10, "o%"), {1}),
        ("score IS NULL", (), {3}),
        ("CAST(score AS DOUBLE PRECISION) >= ? AND items.id < 3", (10,), {2}),
        ("CASE WHEN label COLLATE NOCASE = 'ONE' THEN score ELSE 0 END = 8", (), {1}),
        ("length(label) = 3 AND [score] IN (8, 20)", (), {1, 2}),
        ("score = ? AND '?2 :fake' = '?2 :fake' /* ?5 */ -- ?7", (8,), {1}),
        ("(SELECT score) = ?1", (20,), {2}),
    ],
)
def test_where_expressions(items: Database, condition, args, ids):
    assert {row["id"] for row in items.select("items", condition, *args)} == ids
    assert items.count("items", condition, *args) == len(ids)


def test_subquery_uses_its_own_columns(items: Database):
    items.create_table("rules", (0, "item", int), (0, "score", int))
    items.insert("rules", item=1, score=8)
    items.insert("rules", item=2, score=99)
    condition = (
        "score = (SELECT rules.score FROM rules WHERE item = items.id AND score > ?1)"
    )

    assert items.update("items", condition, 0, label="match") == 1
    assert items.select_one("items", "label = 'match'")["id"] == 1  # pyright: ignore[reportOptionalSubscript]
    assert items.select_one("items", "id = 2")["label"] == "two"  # pyright: ignore[reportOptionalSubscript]


@pytest.mark.parametrize("flexible", [False, True], ids=["strict", "flexible"])
@pytest.mark.parametrize(
    ("condition", "args"),
    [
        ("id = ? AND ? = 7", (2, 7)),
        ("id = ?2 AND ?1 = 7 AND id = ?2", (7, 2)),
        ("id = :wanted AND id = :wanted", (2,)),
        ("id = ?1 AND id = :same AND ? = 7", (2, 2, 7)),
    ],
)
def test_where_bindings_start_after_set_values(db: Database, flexible, condition, args):
    db.create_table("docs", ("p", "id", int), (0, "value", int), flexible=flexible)
    for row_id in (1, 2, 3):
        db.insert("docs", id=row_id, value=0)
    changes = {"value": 99, "payload": [1]} if flexible else {"value": 99}

    assert db.update("docs", condition, *args, **changes) == 1
    assert db.select_one("docs", "id = 2") == {"id": 2, **changes}
    assert {row["id"] for row in db.select("docs", "value = 0")} == {1, 3}


@pytest.mark.parametrize("condition", ["", "  \n"])
def test_writes_require_a_condition(items: Database, condition: str):
    with pytest.raises(ValueError, match="WHERE"):
        items.delete("items", condition)
    with pytest.raises(ValueError, match="WHERE"):
        items.update("items", condition, label="changed")
    assert items.count("items") == 3
    assert items.count("items", "label = 'changed'") == 0


def test_update_requires_values(items: Database):
    with pytest.raises(ValueError, match="value"):
        items.update("items", "id = 1")


def test_many_json_fields_fit_one_update(items: Database):
    # Force more than one json_set call regardless of the SQLite build.
    items._conn.setlimit(sqlite3.SQLITE_LIMIT_FUNCTION_ARG, 7)
    fields = {f"field_{i}": [i, None] for i in range(17)}
    assert items.update("items", "id = ?1", 3, **fields) == 1
    assert items.select_one("items", "id = 3") == {"id": 3, "label": "three", **fields}
    assert items.select_one("items", "id = 2") == {"id": 2, "label": "two", "score": 20}


def test_rename_preserves_managed_and_external_indexes(db: Database):
    db.create_table(
        "old", ("p", "id", int), ("i", 'nick"name', str), ("u", "code", str)
    )
    db.create_index("old", "code")
    db._conn.execute("CREATE INDEX custom_pair ON old (id, code)")
    before = set(db.get_table_indexes("old"))
    assert len(before) == 3 and "custom_pair" in before

    with db:
        db.rename_table("old", "new")
    after = set(db.get_table_indexes("new"))
    assert len(after) == 3 and before & after == {"custom_pair"}
    for column in ('nick"name', "code"):
        db.remove_index("new", column)
    db.remove_index("new", "code")
    assert db.get_table_indexes("new") == ["custom_pair"]
    db.insert("new", code="one")
    with pytest.raises(sqlite3.IntegrityError):
        db.insert("new", code="one")


def test_index_requires_a_real_column(items: Database):
    for name in ("lable", "score"):
        with pytest.raises(sqlite3.OperationalError):
            items.create_index("items", name)
    assert items.get_table_indexes("items") == []
    items.create_index("items", "LABEL")
    (index_name,) = items.get_table_indexes("items")
    assert items._conn.execute(
        "SELECT name FROM pragma_index_info(?)", (index_name,)
    ).fetchall() == [("label",)]


def test_index_on_external_generated_column(db: Database):
    db._conn.execute(
        "CREATE TABLE external (name TEXT, folded TEXT GENERATED ALWAYS AS (lower(name)))"
    )
    db.create_index("external", "folded")
    (index_name,) = db.get_table_indexes("external")
    assert db._conn.execute(
        "SELECT name FROM pragma_index_info(?)", (index_name,)
    ).fetchall() == [("folded",)]


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

    assert items.select_one("items", "score = 42")["id"] == 4  # pyright: ignore[reportOptionalSubscript]


def test_nested_transaction_keeps_outer_transaction_usable(items: Database):
    with items:
        items.update("items", "id = 1", label="outer")
        with pytest.raises(RuntimeError, match="Nested"), items:
            pytest.fail("Nested transaction was accepted")

        items.update("items", "id = 2", label="outer")

    assert items.count("items", "label = 'outer'") == 2


def test_sqlite_initiated_rollback_preserves_original_exception(items: Database):
    with pytest.raises(sqlite3.IntegrityError) as caught, items:
        items.rename_table("items", "pending")
        items._conn.execute("INSERT OR ROLLBACK INTO pending(id) VALUES (1)")

    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY
    assert items.get_tables() == ["items"]
    with items:
        assert items.update("items", "score = 8", label="restored") == 1

    assert items.select_one("items", "id = 1")["label"] == "restored"  # pyright: ignore[reportOptionalSubscript]


def test_failed_commit_rolls_back_and_releases_transaction(tmp_path: Path):
    path = tmp_path / "busy.sqlite"
    with closing(Database(path, timeout=0)) as writer:
        writer.set_journal_mode("DELETE")
        writer.create_table("events", ("p", "id", int))
        with closing(sqlite3.connect(path, isolation_level=None)) as reader:
            reader.execute("BEGIN")
            assert reader.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
            body_finished = False
            with pytest.raises(sqlite3.OperationalError) as caught, writer:
                writer.create_table("pending", (0, "value", int))
                writer.insert("events", id=1)
                body_finished = True

            assert body_finished
            assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY

        assert writer.get_tables() == ["events"]
        assert writer.count("events") == 0
        with pytest.raises(ValueError, match="not registered"):
            writer.insert("pending", value=1)

        with writer:
            writer.insert("events", id=2)

        assert writer.select("events") == [{"id": 2}]


def test_cached_condition_follows_recreated_table(db: Database):
    db.create_table("docs", ("p", "id", int), flexible=True)
    db.insert("docs", id=1, score=10)
    condition = "score = ?"
    assert db.select_one("docs", condition, 10)["id"] == 1  # pyright: ignore[reportOptionalSubscript]
    with db:
        db.delete_table("docs")
        db.create_table("docs", ("p", "id", int), (0, "score", int), flexible=True)
        db.insert("docs", id=2, score=10)

    assert db.select_one("docs", condition, 10)["id"] == 2  # pyright: ignore[reportOptionalSubscript]


def test_journal_mode_and_auto_vacuum_persist(tmp_path: Path):
    path = tmp_path / "pragmas.sqlite"
    with closing(Database(path)) as database:
        database.set_journal_mode("WAL")
        database.set_auto_vacuum("FULL")
        database.vacuum()

    with closing(sqlite3.connect(path)) as raw:
        assert raw.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert raw.execute("PRAGMA auto_vacuum").fetchone() == (1,)


def test_invalid_pragmas_and_unavailable_wal(db: Database):
    with pytest.raises(ValueError):
        db.set_auto_vacuum("invalid")  # pyright: ignore[reportArgumentType]

    with pytest.raises(ValueError):
        db.set_journal_mode("invalid")  # pyright: ignore[reportArgumentType]

    with pytest.raises(RuntimeError):
        db.set_journal_mode("WAL")


def test_incremental_vacuum_frees_pages(tmp_path: Path):
    path = tmp_path / "vacuum.sqlite3"

    with closing(Database(path)) as db:
        db.set_auto_vacuum("INCREMENTAL")
        db.vacuum()

        db.create_table(
            "payloads",
            ("p", "id", int),
            (0, "payload", bytes),
        )

        for _ in range(20):
            db.insert("payloads", payload=b"x" * 4096)

        db.delete("payloads", "1")

        before = db._conn.execute("PRAGMA freelist_count").fetchone()[0]
        assert before > 2

        db.incremental_vacuum(2)

        after_limit = db._conn.execute("PRAGMA freelist_count").fetchone()[0]

        assert before - 2 <= after_limit < before

        db.incremental_vacuum()

        after_all = db._conn.execute("PRAGMA freelist_count").fetchone()[0]

        assert after_all == 0


@pytest.mark.parametrize(
    "pages",
    [0, -1, True, 1.5, "10"],
)
def test_incremental_vacuum_invalid_pages(db: Database, pages):
    with pytest.raises(ValueError, match="Pages"):
        db.incremental_vacuum(pages)


def test_close_releases_connection():
    db = Database(":memory:")
    db.close()
    with pytest.raises(sqlite3.ProgrammingError):
        db.get_tables()

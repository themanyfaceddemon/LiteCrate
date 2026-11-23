import pytest

from litecrate import Database


def test_insert_without_values_uses_column_defaults(db: Database):
    db.create_table("events", ("p", "id", int), (0, "note"))

    row_id = db.insert("events")

    assert isinstance(row_id, int)
    assert db.select_one("events", "id = ?", row_id) == {"id": row_id, "note": None}
    assert db.count("events", "  ") == 1


def test_insert_pairs_values_with_columns_in_any_keyword_order(db: Database):
    db.create_table("people", (0, "first_name", str), (0, "last_name", str))
    db.insert("people", first_name="Ada", last_name="Lovelace")
    db.insert("people", last_name="Hopper", first_name="Grace")

    assert db.select_one("people", "first_name = ?", "Ada") == {
        "first_name": "Ada",
        "last_name": "Lovelace",
    }
    assert db.select_one("people", "first_name = ?", "Grace") == {
        "first_name": "Grace",
        "last_name": "Hopper",
    }


def test_filter_without_matches_leaves_existing_rows_untouched(db: Database):
    db.create_table("events", ("p", "id", int), (0, "note", str))
    db.insert("events", id=1, note="original")

    assert db.select("events", "id < 0") == []
    assert db.select_one("events", "id < 0") is None
    assert db.count("events", "id < 0") == 0
    assert db.update("events", "id < 0", note="unused") == 0
    assert db.delete("events", "id < 0") == 0
    assert db.select("events") == [{"id": 1, "note": "original"}]


def test_crud_affects_only_matching_rows(db: Database):
    db.create_table("users", ("p", "id", int), (0, "team", str))
    for user_id, team in [(1, "red"), (2, "blue"), (3, "red")]:
        assert db.insert("users", id=user_id, team=team) == user_id

    assert {row["id"] for row in db.select("users", "team = ?", "red")} == {1, 3}
    assert db.update("users", "team = ?", "red", team="green") == 2
    assert db.count("users", "team = ?", "green") == 2
    assert db.delete("users", "team = ?", "green") == 2
    assert db.select("users") == [{"id": 2, "team": "blue"}]


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
    ids=[
        "dict-column-rejects-list",
        "list-column-rejects-dict",
        "json-rejects-nan",
        "json-rejects-bytes",
        "reserved-field-name",
        "duplicate-column",
        "duplicate-flexible-field",
    ],
)
def test_invalid_values_do_not_write_partial_rows(
    db: Database, values: dict[str, object], error: type[Exception]
):
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


@pytest.mark.parametrize("condition", ["", "  \n"], ids=["empty", "whitespace"])
@pytest.mark.parametrize(
    ("method", "changes"), [("delete", {}), ("update", {"label": "changed"})]
)
def test_filtered_writes_reject_a_blank_condition(
    items: Database, condition: str, method: str, changes: dict[str, object]
):
    with pytest.raises(ValueError, match="WHERE"):
        getattr(items, method)("items", condition, **changes)

    assert items.count("items") == 3
    assert items.count("items", "label = 'changed'") == 0


@pytest.mark.parametrize(("method", "args"), [("update", ("id = 1",)), ("update_all", ())])
def test_update_requires_values(items: Database, method: str, args: tuple[str, ...]):
    with pytest.raises(ValueError, match="value"):
        getattr(items, method)("items", *args)


def test_update_all_changes_every_row(items: Database):
    assert items.update_all("ITEMS", label="changed", tags=["new"]) == 3
    updated = [(row["label"], row["tags"]) for row in items.select("items")]
    assert updated == [("changed", ["new"])] * 3
    assert items.count("items", "score = ?", 8) == 1


def test_delete_all_removes_every_row(items: Database):
    assert items.delete_all("ITEMS") == 3
    assert items.select("items") == []


def test_bulk_writes_report_zero_for_an_empty_table(db: Database):
    db.create_table("items", (0, "label", str))

    assert db.update_all("items", label="changed") == 0
    assert db.delete_all("items") == 0
    assert db.select_one("items") is None

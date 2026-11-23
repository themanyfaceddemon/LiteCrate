import pytest

from litecrate import Database


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
    assert row is not None and row["extra"] is False
    assert items.delete("items", "score = ?", 20) == 1
    assert items.select_one("items", "id = 3") == {"id": 3, "label": "three"}


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


def test_one_update_can_write_many_flexible_fields(items: Database):
    fields = {f"field_{i}": [i, None] for i in range(128)}
    assert items.update("items", "id = ?1", 3, **fields) == 1
    assert items.select_one("items", "id = 3") == {"id": 3, "label": "three", **fields}
    assert items.select_one("items", "id = 2") == {"id": 2, "label": "two", "score": 20}

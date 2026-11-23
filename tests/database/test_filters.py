import pytest

from litecrate import Database


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
    assert [row["id"] for row in items.select("items", "label = 'match'")] == [1]
    assert items.select_one("items", "id = 2") == {"id": 2, "label": "two", "score": 20}


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
def test_update_uses_filter_parameters_to_match_the_expected_row(
    db: Database, flexible: bool, condition: str, args: tuple[object, ...]
):
    db.create_table("docs", ("p", "id", int), (0, "value", int), flexible=flexible)
    for row_id in (1, 2, 3):
        db.insert("docs", id=row_id, value=0)
    changes = {"value": 99, "payload": [1]} if flexible else {"value": 99}

    assert db.update("docs", condition, *args, **changes) == 1
    assert db.select_one("docs", "id = 2") == {"id": 2, **changes}
    assert {row["id"] for row in db.select("docs", "value = 0")} == {1, 3}


def test_filter_reads_current_column_definition_after_recreating_a_table(db: Database):
    db.create_table("docs", ("p", "id", int), flexible=True)
    db.insert("docs", id=1, score=10)
    condition = "score = ?"
    assert db.select_one("docs", condition, 10) == {"id": 1, "score": 10}
    with db:
        db.delete_table("docs")
        db.create_table("docs", ("p", "id", int), (0, "score", int), flexible=True)
        db.insert("docs", id=2, score=10)

    assert db.select_one("docs", condition, 10) == {"id": 2, "score": 10}

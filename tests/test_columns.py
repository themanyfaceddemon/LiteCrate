import pytest

from src.litecrate.utils.colum_unils import (
    INDEX_BIT,
    NOT_NULL_BIT,
    PRIMARY_BIT,
    UNIQUE_BIT,
    parse_column,
)


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        ("name", (0, "name", None)),
        (":name", (0, "name", None)),
        (":name:", (0, "name", None)),
        ("I:name", (INDEX_BIT, "name", None)),
        ("i:name:", (INDEX_BIT, "name", None)),
        ("n:name:text", (NOT_NULL_BIT, "name", "TEXT")),
        ("PU:name:integer", (PRIMARY_BIT | UNIQUE_BIT, "name", "INTEGER")),
        (
            "pInU:Login:TEXT",
            (PRIMARY_BIT | INDEX_BIT | NOT_NULL_BIT | UNIQUE_BIT, "Login", "TEXT"),
        ),
        ("iiii:name:blob", (INDEX_BIT, "name", "BLOB")),
    ],
)
def test_parse_column_valid(definition, expected):
    assert parse_column(definition) == expected


@pytest.mark.parametrize(
    ("alias", "sqlite_type"),
    [
        ("float", "REAL"),
        ("real", "REAL"),
        ("FLOAT", "REAL"),
        ("bool", "INTEGER"),
        ("int", "INTEGER"),
        ("integer", "INTEGER"),
        ("INTEGER", "INTEGER"),
        ("str", "TEXT"),
        ("text", "TEXT"),
        ("TeXt", "TEXT"),
        ("bytes", "BLOB"),
        ("blob", "BLOB"),
        ("BLOB", "BLOB"),
        ("", None),
    ],
)
def test_column_type_aliases(alias, sqlite_type):
    assert parse_column(f":value:{alias}") == (0, "value", sqlite_type)


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        ("", "Empty column name"),
        (":", "Empty column name"),
        ("::", "Empty column name"),
        ("i::TEXT", "Empty column name"),
        ("_data", "reserved"),
        ("I:_DATA:TEXT", "reserved"),
        ("na\x00me", "Invalid column name"),
        ("x:name:TEXT", "Unknown column flag"),
        ("iiiii:name:TEXT", "Too many column flags"),
        ("i:name:datetime", "Unknown column type"),
        ("i:name:INTEGER:extra", "expected 1 to 3 parts"),
    ],
)
def test_parse_column_invalid(definition, message):
    with pytest.raises(ValueError, match=message):
        parse_column(definition)


def test_flag_bits_are_distinct_powers_of_two():
    flags = [NOT_NULL_BIT, UNIQUE_BIT, PRIMARY_BIT, INDEX_BIT]
    assert len(set(flags)) == 4
    assert all(flag > 0 and flag & (flag - 1) == 0 for flag in flags)


def test_omitted_type_is_not_explicit_blob():
    assert parse_column("i:data") == (INDEX_BIT, "data", None)
    assert parse_column("i:data:") == (INDEX_BIT, "data", None)
    assert parse_column("i:data:BLOB") == (INDEX_BIT, "data", "BLOB")

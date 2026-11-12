import sqlite3

import pytest

from src.litecrate.utils import sanitize_identifier


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("users", '"users"'),
        ("UserName", '"UserName"'),
        ("123", '"123"'),
        ("user name", '"user name"'),
        ("user.name", '"user.name"'),
        ("имя", '"имя"'),
        ("select", '"select"'),
        ('a"b', '"a""b"'),
        ('""', '""""""'),
        ("users; DROP TABLE accounts;", '"users; DROP TABLE accounts;"'),
    ],
)
def test_sanitize_identifier_valid(value: str, expected: str):
    assert sanitize_identifier(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "\0",
        "user\0name",
        "\0users",
        "users\0",
    ],
)
def test_sanitize_identifier_invalid(value: str):
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        sanitize_identifier(value)


def test_sanitize_identifier_sql_injection():
    payload = 'users"; DROP TABLE accounts; --'
    conn = sqlite3.connect(":memory:")

    try:
        conn.execute("CREATE TABLE accounts (id INTEGER)")
        conn.execute(f"CREATE TABLE {sanitize_identifier(payload)} (id INTEGER)")

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }

        assert "accounts" in tables
        assert payload in tables

    finally:
        conn.close()

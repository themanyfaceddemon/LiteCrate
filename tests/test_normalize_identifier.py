
import pytest

from litecrate.utils.identifier import normalize_identifier


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("users", "users"),
        ("USERS", "users"),
        ("UserName", "username"),
        ("uSeRs", "users"),
        ("123", "123"),
        ("user name", "user name"),
        ("user.name", "user.name"),
        ("select", "select"),
        ('a"b', 'a"b'),
        ('""', '""'),
        ("", ""),
        ("\x01\x02", "\x01\x02"),
        ("users; DROP TABLE accounts;", "users; drop table accounts;"),
    ],
)
def test_normalize_identifier_valid(value: str, expected: str):
    assert normalize_identifier(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "\0",
        "user\0name",
        "\0users",
        "users\0",
        "имя",
        "Üsers",
        "users_猫",
        "user😀",
    ],
)
def test_normalize_identifier_invalid(value: str):
    with pytest.raises(ValueError, match="Invalid SQL"):
        normalize_identifier(value)


def test_normalize_identifier_idempotent():
    value = 'UsEr"NaMe'

    normalized = normalize_identifier(value)

    assert normalize_identifier(normalized) == normalized

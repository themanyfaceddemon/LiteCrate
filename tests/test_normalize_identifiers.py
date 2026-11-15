import pytest

from src.litecrate.utils.identifier import normalize_identifiers


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((), ()),
        (("Users",), ("users",)),
        (("Users", "Login"), ("users", "login")),
        (("ABC", "DEF", "GHI"), ("abc", "def", "ghi")),
        (("", "USERS"), ("", "users")),
        (("123", "User.Name"), ("123", "user.name")),
        (("\x01", "UPPER"), ("\x01", "upper")),
    ],
)
def test_normalize_identifiers_valid(values, expected):
    assert normalize_identifiers(*values) == expected


@pytest.mark.parametrize(
    "values",
    [
        ("имя",),
        ("users", "имя"),
        ("имя", "users"),
        ("USERS", "login\0"),
        ("user\0", "login"),
        ("users", "login", "猫"),
    ],
)
def test_normalize_identifiers_invalid(values):
    with pytest.raises(ValueError, match="Invalid SQL"):
        normalize_identifiers(*values)


def test_normalize_identifiers_returns_tuple():
    assert isinstance(normalize_identifiers("Users"), tuple)
    assert isinstance(normalize_identifiers("Users", "ID"), tuple)
    assert isinstance(normalize_identifiers(), tuple)

import pytest

from litecrate.utils import (
    check_column_name,
    check_table_name,
    normalize_identifier,
    normalize_identifiers,
    sanitize_identifier,
    sanitize_identifiers,
)


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
        ("", '""'),
        ("\0", '"\0"'),
        ("\x01\x02", '"\x01\x02"'),
        ("users; DROP TABLE accounts;", '"users; DROP TABLE accounts;"'),
    ],
)
def test_sanitize_identifier_valid(value: str, expected: str):
    assert sanitize_identifier(value) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            (),
            (),
        ),
        (
            ("users",),
            ('"users"',),
        ),
        (
            ("users", "login"),
            ('"users"', '"login"'),
        ),
        (
            ("UserName", 'a"b', "имя"),
            ('"UserName"', '"a""b"', '"имя"'),
        ),
        (
            ('""', "select"),
            ('""""""', '"select"'),
        ),
        (
            ("", "\0"),
            ('""', '"\0"'),
        ),
        (
            ("users; DROP TABLE accounts;", "id"),
            ('"users; DROP TABLE accounts;"', '"id"'),
        ),
    ],
)
def test_sanitize_identifiers_valid(values, expected):
    assert sanitize_identifiers(*values) == expected


def test_sanitize_identifiers_returns_tuple():
    assert isinstance(sanitize_identifiers("users"), tuple)
    assert isinstance(sanitize_identifiers("users", "id"), tuple)
    assert isinstance(sanitize_identifiers(), tuple)


@pytest.mark.parametrize(
    "names",
    [
        (),
        ("id",),
        ("username",),
        ("_litecrate_meta",),
        ("id", "username"),
        ("id", "username", "password"),
        ("",),
        ("имя",),
        ("_database",),
    ],
)
def test_check_column_name_valid(names):
    assert check_column_name(*names) is None


@pytest.mark.parametrize(
    "names",
    [
        ("_data",),
        ("_DATA",),
        ("_Data",),
        ("id", "_data"),
        ("_data", "username"),
        ("id", "username", "_DATA"),
    ],
)
def test_check_column_name_reserved(names):
    with pytest.raises(ValueError, match="reserved"):
        check_column_name(*names)


@pytest.mark.parametrize(
    "names",
    [
        (),
        ("users",),
        ("_data",),
        ("users", "accounts"),
        ("users", "accounts", "sessions"),
        ("",),
        ("имя",),
        ("_litecrate_metadata",),
    ],
)
def test_check_table_name_valid(names):
    assert check_table_name(*names) is None


@pytest.mark.parametrize(
    "names",
    [
        ("_litecrate_meta",),
        ("_LITECRATE_META",),
        ("_LiteCrate_Meta",),
        ("users", "_litecrate_meta"),
        ("_litecrate_meta", "users"),
        ("users", "accounts", "_LITECRATE_META"),
    ],
)
def test_check_table_name_reserved(names):
    with pytest.raises(ValueError, match="reserved"):
        check_table_name(*names)

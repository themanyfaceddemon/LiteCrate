import pytest

from src.litecrate.utils.identifier import sanitize_identifiers


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

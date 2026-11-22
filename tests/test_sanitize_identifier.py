import pytest

from litecrate.utils.identifier import sanitize_identifier


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

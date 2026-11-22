import pytest

from litecrate.utils.identifier import check_column_name


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

import pytest

from litecrate.utils.identifier import check_table_name


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

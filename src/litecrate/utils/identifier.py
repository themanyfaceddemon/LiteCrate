from hashlib import blake2s


# region normalize
def normalize_identifier(identifier: str) -> str:
    if not identifier.isascii() or "\0" in identifier:
        raise ValueError(f"Invalid SQL {identifier=}")

    return identifier.lower()


def normalize_identifiers(*identifiers: str) -> tuple[str, ...]:
    result = []

    for identifier in identifiers:
        if not identifier.isascii() or "\0" in identifier:
            raise ValueError(f"Invalid SQL {identifier=}")

        result.append(identifier.lower())

    return tuple(result)


# endregion


# region sanitize
def sanitize_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sanitize_identifiers(*identifiers: str) -> tuple[str, ...]:
    return tuple(
        '"' + identifier.replace('"', '""') + '"' for identifier in identifiers
    )


# endregion


# region check
def check_table_name(*names: str) -> None:
    for name in names:
        if name.lower() == "_litecrate_meta":
            raise ValueError("Table name '_litecrate_meta' is reserved")


def check_column_name(*names: str) -> None:
    for name in names:
        if name.lower() == "_data":
            raise ValueError("Column name '_data' is reserved")


# endregion


def get_index_identifier(table: str, colum: str) -> str:
    return f"idx_{blake2s(f'{table}\0{colum}'.encode(), digest_size=16).hexdigest()}"


__all__ = [
    "check_column_name",
    "check_table_name",
    "get_index_identifier",
    "normalize_identifier",
    "normalize_identifiers",
    "sanitize_identifier",
    "sanitize_identifiers",
]

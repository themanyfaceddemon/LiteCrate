from .identifier import (
    get_index_identifier,
    normalize_identifiers,
    sanitize_identifiers,
)

_INDEX = 1 << 0
_NOT_NULL = 1 << 1
_PRIMARY = 1 << 2
_UNIQUE = 1 << 3
_AUTOINCREMENT = 1 << 4
_FLAGS = {"i": _INDEX, "n": _NOT_NULL, "p": _PRIMARY, "u": _UNIQUE, "a": _AUTOINCREMENT}
_ALL_FLAGS = sum(_FLAGS.values())


_SQL_TYPES = {
    int: "INTEGER",
    bool: "INTEGER",
    float: "REAL",
    str: "TEXT",
    bytes: "BLOB",
    None: "",
}


def _get_colum_type(colum_type: type | None) -> str:
    if colum_type not in _SQL_TYPES:
        raise TypeError(f"Unsupported column type: {colum_type!r}")

    return _SQL_TYPES[colum_type]


def _sanitize_flags(flags: str | int) -> int:
    match flags:
        case int():
            bit_mask = int(flags)

        case str():
            bit_mask = 0
            for char in flags.lower():
                try:
                    bit_mask |= _FLAGS[char]

                except KeyError:
                    raise ValueError(
                        f"Unknown column flag {char!r} in {flags!r}"
                    ) from None

        case _:
            raise TypeError(f"Flags must be str or int, got {type(flags).__name__}")

    if bit_mask & ~_ALL_FLAGS:
        raise ValueError(f"Invalid column flag mask: {flags!r}")

    if bit_mask & _AUTOINCREMENT:
        bit_mask |= _PRIMARY

    if bit_mask & _PRIMARY:
        bit_mask &= ~(_INDEX | _UNIQUE)

    elif bit_mask & _UNIQUE:
        bit_mask &= ~_INDEX

    return bit_mask


def parse_colum_into_sql(
    table_name: str,
    flags: str | int,
    colum_name: str,
    colum_type: type | None = None,
) -> tuple[str, str | None]:
    table_name, colum_name = normalize_identifiers(table_name, colum_name)
    san_table_name, san_colum_name = sanitize_identifiers(table_name, colum_name)

    flags = _sanitize_flags(flags)
    if flags & _AUTOINCREMENT and colum_type is not int:
        raise ValueError("AUTOINCREMENT requires a column of type int")

    type_sql = _get_colum_type(colum_type)

    # region index sql create
    index_sql = None
    if flags & _INDEX:
        index_sql = f"CREATE INDEX {get_index_identifier(table_name, colum_name)} ON {san_table_name} ({san_colum_name})"
    # endregion

    # region colum_sql_create
    colum_sql = f"{san_colum_name} {type_sql}".rstrip()
    if flags & _PRIMARY:
        colum_sql += " PRIMARY KEY"

    if flags & _AUTOINCREMENT:
        colum_sql += " AUTOINCREMENT"

    if flags & _NOT_NULL:
        colum_sql += " NOT NULL"

    if flags & _UNIQUE:
        colum_sql += " UNIQUE"
    # endregion

    return colum_sql, index_sql


__all__ = [
    "parse_colum_into_sql",
]

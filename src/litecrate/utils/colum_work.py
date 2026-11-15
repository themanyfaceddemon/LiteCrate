from enum import IntFlag

from .identifier import (
    get_index_identifier,
    normalize_identifiers,
    sanitize_identifiers,
)


class ColumBitEnum(IntFlag):
    INDEX = 1 << 0
    NOT_NULL = 1 << 1
    PRIMARY = 1 << 2
    UNIQUE = 1 << 3

    @staticmethod
    def all_flags() -> int:
        return sum(flag.value for flag in ColumBitEnum)


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
            bit_mask = flags

        case str():
            bit_mask = 0
            for char in flags.lower():
                if char == "p":
                    bit_mask |= ColumBitEnum.PRIMARY
                    continue

                elif char == "i":
                    bit_mask |= ColumBitEnum.INDEX
                    continue

                elif char == "n":
                    bit_mask |= ColumBitEnum.NOT_NULL
                    continue

                elif char == "u":
                    bit_mask |= ColumBitEnum.UNIQUE
                    continue

                else:
                    raise ValueError(f"Unknown column flag {char!r} in {flags!r}")

        case _:
            raise TypeError(f"Flags must be str or int, got {type(flags).__name__}")

    if bit_mask & ~ColumBitEnum.all_flags():
        raise ValueError(f"Invalid column flag mask: {flags!r}")

    if bit_mask & ColumBitEnum.PRIMARY:
        bit_mask &= ~(ColumBitEnum.INDEX | ColumBitEnum.UNIQUE)

    elif bit_mask & ColumBitEnum.UNIQUE:
        bit_mask &= ~ColumBitEnum.INDEX

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
    type_sql = _get_colum_type(colum_type)

    # region index sql create
    index_sql = None
    if flags & ColumBitEnum.INDEX:
        index_sql = f"CREATE INDEX {get_index_identifier(table_name, colum_name)} ON {san_table_name} ({san_colum_name})"
    # endregion

    # region colum_sql_create
    colum_sql = f"{san_colum_name} {type_sql}".rstrip()
    if flags & ColumBitEnum.PRIMARY:
        colum_sql += " PRIMARY KEY"

    if flags & ColumBitEnum.NOT_NULL:
        colum_sql += " NOT NULL"

    if flags & ColumBitEnum.UNIQUE:
        colum_sql += " UNIQUE"
    # endregion

    return colum_sql, index_sql


__all__ = [
    "ColumBitEnum",
    "parse_colum_into_sql",
]

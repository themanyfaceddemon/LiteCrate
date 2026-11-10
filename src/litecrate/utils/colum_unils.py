INDEX_BIT: int = 1 << 3
NOT_NULL_BIT: int = 1 << 0
PRIMARY_BIT: int = 1 << 2
UNIQUE_BIT: int = 1 << 1


def _column_flag(value: str) -> int:
    """
    support chars: pinu
    """

    if len(value) > 4:
        raise ValueError(f"Too many column flags in {value}")

    bit_mask = 0

    for char in value.lower():
        if char == "p":
            bit_mask |= PRIMARY_BIT
            continue

        elif char == "i":
            bit_mask |= INDEX_BIT
            continue

        elif char == "n":
            bit_mask |= NOT_NULL_BIT
            continue

        elif char == "u":
            bit_mask |= UNIQUE_BIT
            continue

        else:
            raise ValueError(f"Unknown column flag {char} in {value}")

    return bit_mask


def _column_type(value: str) -> str | None:
    """support (case-insensitive)

    float -> REAL;
    real  -> REAL

    bool    -> INTEGER;
    int     -> INTEGER;
    integer -> INTEGER

    str  -> TEXT;
    text -> TEXT

    bytes -> BLOB;
    blob  -> BLOB

    empty_str -> None
    """

    # Это тупая проверка литералов. Ибо мне влом писать проверку в parce_column
    value = value.lower()

    if value in ("float", "real"):
        return "REAL"

    if value in ("bool", "int", "integer"):
        return "INTEGER"

    if value in ("str", "text"):
        return "TEXT"

    if value in ("bytes", "blob"):
        return "BLOB"

    if value == "":
        return None

    raise ValueError(f"Unknown column type {value}")


def _column_name(value: str) -> str:
    """
    no _data name;
    no `\\0` char in name
    """

    if not value:
        raise ValueError("Empty column name")

    if "\0" in value:
        raise ValueError(f"Invalid column name {value!r}")

    if value.lower() == "_data":
        raise ValueError("_data column reserved by the library")

    return value


def parse_column(raw_column: str) -> tuple[int, str, str | None]:
    parts = raw_column.split(":")

    len_parts = len(parts)
    if len_parts > 3:
        raise ValueError(
            f"Invalid column definition {raw_column!r}: "
            f"expected 1 to 3 parts, got {len_parts}."
        )

    column_mask: int = 0
    column_name: str = ""
    column_type: str | None = None

    if len_parts == 3:
        column_mask = _column_flag(parts[0])
        column_name = _column_name(parts[1])
        column_type = _column_type(parts[2])

    elif len_parts == 2:
        column_mask = _column_flag(parts[0])
        column_name = _column_name(parts[1])

    elif len_parts == 1:
        column_name = _column_name(parts[0])

    return column_mask, column_name, column_type


__all__ = [
    "INDEX_BIT",
    "NOT_NULL_BIT",
    "PRIMARY_BIT",
    "UNIQUE_BIT",
    "parse_column",
]

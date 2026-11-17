import base64
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

# region Binary tags
_BT_BYTES = b"\x00"
_BT_PATH = b"\x01"
# endregion


# region Utilities
def _write_varint(out: bytearray, value: int) -> None:
    if value < 0:
        raise ValueError("Varint cannot be negative")

    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7

    out.append(value)


def _read_exact(file: BinaryIO, size: int) -> bytes:
    data = file.read(size)

    if len(data) != size:
        raise ValueError("Unexpected end of binary data")

    return data


def _read_varint(file: BinaryIO) -> int:
    value = 0
    shift = 0

    while True:
        byte = _read_exact(file, 1)[0]
        value |= (byte & 0x7F) << shift

        if not byte & 0x80:
            return value

        shift += 7


# endregion


# Serialization
def _write_obj(out: bytearray, obj: Any) -> None:
    match obj:
        case bytes():
            out.extend(_BT_BYTES)
            _write_varint(out, len(obj))
            out.extend(obj)

        case Path():
            out.extend(_BT_PATH)
            data = str(obj).encode("utf-8")
            _write_varint(out, len(data))
            out.extend(data)

        case _:
            raise TypeError(f"Unsupported type: {type(obj)}")


# Deserialization
def _read_obj(file: BinaryIO) -> Any:
    tag = _read_exact(file, 1)

    if tag == _BT_BYTES:
        size = _read_varint(file)
        return _read_exact(file, size)

    elif tag == _BT_PATH:
        size = _read_varint(file)
        return Path(_read_exact(file, size).decode("utf-8"))

    else:
        raise ValueError(f"Unknown binary tag: {tag!r}")


# Public API
# region base64
def dumps_base64(obj: Any) -> str:
    out = bytearray()
    _write_obj(out, obj)
    return base64.b64encode(out).decode("ascii")


def loads_base64(data: str) -> Any:
    file = BytesIO(base64.b64decode(data, validate=True))
    result = _read_obj(file)

    if file.read(1):
        raise ValueError("Unexpected trailing binary data")

    return result


# endregion

# region json stuff
MARKER = "\x00"


def json_encode(obj):
    if isinstance(obj, (bytes, Path)):
        return {MARKER: dumps_base64(obj)}

    raise TypeError(f"Unsupported type: {type(obj)}")


def json_decode(obj):
    if len(obj) == 1 and MARKER in obj:
        return loads_base64(obj[MARKER])

    return obj


# endregion

# TODO: datetime? decimal?
# decimal смысла нет ибо по факту str существует

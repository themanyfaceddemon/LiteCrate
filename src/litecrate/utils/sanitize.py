def sanitize_identifier(value: str) -> str:
    if not value or "\0" in value:
        raise ValueError(f"Invalid SQL identifier: {value!r}")

    return '"' + value.replace('"', '""') + '"'


__all__ = [
    "sanitize_identifier",
]

import json
import re
from collections.abc import Collection
from functools import lru_cache

from .identifier import normalize_identifier, sanitize_identifier, sanitize_identifiers

JSON_ENCODER = json.JSONEncoder(
    ensure_ascii=False,
    allow_nan=False,
    separators=(",", ":"),
)


# Recognize strings, comments, names and parameters in a WHERE expression.
_WHERE_TOKENS = re.compile(
    r"(?P<comment>--[^\n]*|/\*.*?(?:\*/|\Z))"
    r"|(?P<literal>[xX]?'(?:''|[^'])*(?:'|\Z))"
    r'|(?P<quoted>"(?:""|[^"])*"|`(?:``|[^`])*`|\[[^\]]*\])'
    r'|(?P<unfinished>["`\[].*\Z)'
    r"|(?P<param>\?[0-9]*|[:@$][\w$\x80-\U0010ffff]+"
    r"(?:::[\w$\x80-\U0010ffff]*)*(?:\([^\s)]*\))?)"
    r"|(?P<number>0[xX][0-9a-fA-F_]+|(?:[0-9][0-9_]*(?:\.[0-9_]*)?"
    r"|\.[0-9][0-9_]*)(?:[eE][+-]?[0-9][0-9_]*)?)"
    r"|(?P<word>[A-Za-z_\x80-\U0010ffff][\w$\x80-\U0010ffff]*)"
    r"|(?P<other>\S)",
    re.DOTALL,
)

# Fast check for named and numbered bind parameters such as :name and ?1.
_EXPLICIT_BIND = re.compile(r"\?[0-9]|[:@$]")

# Preserve SQLite keywords, literals, and row ID aliases.
_SQL_WORDS = frozenset(
    [
        "AND",
        "OR",
        "NOT",
        "IS",
        "NULL",
        "TRUE",
        "FALSE",
        "BETWEEN",
        "IN",
        "LIKE",
        "GLOB",
        "REGEXP",
        "MATCH",
        "ESCAPE",
        "EXISTS",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "CAST",
        "AS",
        "COLLATE",
        "DISTINCT",
        "ALL",
        "SELECT",
        "FROM",
        "WHERE",
        "GROUP",
        "BY",
        "HAVING",
        "ORDER",
        "LIMIT",
        "OFFSET",
        "ASC",
        "DESC",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "JOIN",
        "ON",
        "USING",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "CROSS",
        "NATURAL",
        "WITH",
        "RECURSIVE",
        "VALUES",
        "NULLS",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "ISNULL",
        "NOTNULL",
        "FILTER",
        "OVER",
        "PARTITION",
        "ROWS",
        "RANGE",
        "UNBOUNDED",
        "PRECEDING",
        "FOLLOWING",
        "EXCLUDE",
        "TIES",
        "OTHERS",
        "GROUPS",
        "ROWID",
        "OID",
        "_ROWID_",
        "RETURNING",
        "INDEXED",
        "INDEX",
        "IF",
    ]
)


@lru_cache(maxsize=128)
def build_insert_sql(table_name: str, columns: tuple[str, ...]) -> str:
    """Build an INSERT statement for an ordered tuple of SQL columns."""

    table = sanitize_identifier(table_name)
    if not columns:
        return f"INSERT INTO {table} DEFAULT VALUES"

    names = ", ".join(sanitize_identifiers(*columns))
    placeholders = ", ".join(["?"] * len(columns))
    return f"INSERT INTO {table} ({names}) VALUES ({placeholders})"


def json_path(name: str) -> str:
    """Encode a field name as a single top-level SQLite JSON path key."""

    label = JSON_ENCODER.encode(name)[1:-1].replace(r"\"", r"\u0022")
    return f'$."{label}"'


def json_field_expression(name: str) -> str:
    path = json_path(name).replace("'", "''")
    return f"""json_extract("_data", '{path}')"""


def _local_subqueries(tokens: list[re.Match[str]]) -> set[int]:
    """Locate subqueries whose local identifiers must not be rewritten."""

    groups: list[int] = []
    local: set[int] = set()
    for i, token in enumerate(tokens):
        raw = token[0]
        if raw == "(":
            groups.append(i)

        elif raw == ")" and groups:
            groups.pop()

        elif groups and raw.upper() in ("FROM", "WITH", "AS"):
            if raw.upper() == "FROM" and tokens[i - 1][0].upper() == "DISTINCT":
                continue

            opening = groups[-1]
            if tokens[opening + 1][0].upper() in ("SELECT", "WITH"):
                local.add(opening)

    return local


@lru_cache(maxsize=128)
def _query_parts(query: str) -> tuple[tuple[int, int, str | int], ...]:
    """Parse reusable SQL token spans for bind parameters and field names.

    String literals and comments are excluded from identifier rewriting.
    The result is cached by the original condition string.
    """

    tokens = [
        token for token in _WHERE_TOKENS.finditer(query) if token.lastgroup != "comment"
    ]
    parts: list[tuple[int, int, str | int]] = []
    last_slot = 0
    named_slots: dict[str, int] = {}
    skip_depth = 0
    upper_query = query.upper()
    local: set[int] = set()
    if "SELECT" in upper_query or "WITH" in upper_query:
        local = _local_subqueries(tokens)

    for i, token in enumerate(tokens):
        raw = token[0]
        kind = token.lastgroup

        if kind == "unfinished":
            return ()  # Let SQLite report the malformed expression.

        if kind == "param":
            if raw == "?":
                last_slot += 1
                continue

            if raw[0] == "?":
                slot = int(raw[1:])
                last_slot = max(last_slot, slot)

            else:
                if raw not in named_slots:
                    last_slot += 1
                    named_slots[raw] = last_slot

                slot = named_slots[raw]

            parts.append((*token.span(), slot))
            continue

        # Leave local SQL names and multi-word CAST type names intact.
        if skip_depth:
            if raw == "(":
                skip_depth += 1

            elif raw == ")":
                skip_depth -= 1

            continue

        if i in local:
            skip_depth = 1
            continue

        if kind == "word" and raw.upper() == "AS":
            skip_depth = 1
            continue

        if kind not in ("word", "quoted"):
            continue

        previous = tokens[i - 1][0].upper() if i else ""
        following = tokens[i + 1][0] if i + 1 < len(tokens) else ""
        if previous in (".", "COLLATE", "IN") or following in (".", "("):
            continue

        if kind == "word":
            if raw.upper() in _SQL_WORDS or previous == "NULLS":
                continue

            name = raw

        elif raw[0] == "[":
            name = raw[1:-1]

        else:
            name = raw[1:-1].replace(raw[0] * 2, raw[0])

        if name.isascii() and "\0" not in name:
            parts.append((*token.span(), normalize_identifier(name)))

    return tuple(parts)


def rewrite_where(
    query: str,
    columns: Collection[str] | None,
    bind_offset: int = 0,
) -> str:
    """Prepare a WHERE expression for SQLite.

    For a flexible table, a field outside its declared columns is read
    through ``json_extract`` on ``_data``. For example, ``score = ?`` becomes
    ``json_extract("_data", '$."score"') = ?`` when ``score`` is a flexible
    field. Pass ``None`` for the columns of a regular table.

    Numbered and named parameters are adjusted by the number of parameters
    before WHERE. In an update with one bound value in SET, ``id = ?1``
    becomes ``id = ?2``.
    """

    if columns is None and not _EXPLICIT_BIND.search(query):
        return query

    result: list[str] = []
    end = 0
    for start, stop, part in _query_parts(query):
        if isinstance(part, int):
            if part == 0 or (bind_offset == 0 and query[start] == "?"):
                continue

            replacement = f"?{part + bind_offset}"

        elif columns is not None and part not in columns:
            replacement = json_field_expression(part)

        else:
            continue

        result.append(query[end:start])
        result.append(replacement)
        end = stop

    if not result:
        return query

    result.append(query[end:])
    return "".join(result)

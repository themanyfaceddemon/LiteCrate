import json
import re
import sqlite3
from functools import lru_cache
from itertools import batched
from pathlib import Path
from types import TracebackType
from typing import Literal, Self
from urllib.parse import quote, unquote

from ..utils import (
    check_column_name,
    check_table_name,
    get_index_identifier,
    normalize_identifier,
    normalize_identifiers,
    parse_colum_into_sql,
    sanitize_identifier,
    sanitize_identifiers,
)


class Database:
    _QUERY_TOKENS = re.compile(
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
    _SPECIAL_BIND = re.compile(r"\?[0-9]|[:@$]")
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

    _CACHE_TYPES: dict[str, type | None] = {
        "None": None,
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "bytes": bytes,
        "dict": dict,
        "list": list,
    }

    def __init__(
        self,
        db_path: Path | str | Literal[":memory:"],
        timeout: float = 30.0,
    ) -> None:
        self._conn = sqlite3.connect(
            str(db_path),
            timeout=timeout,
            isolation_level=None,
            autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,  # pyright: ignore[reportArgumentType]
            check_same_thread=False,
        )

        self._cache: dict[str, dict[str, type | None]] = {}
        self._rollback_cache: dict[str, dict[str, type | None]] | None = None

        try:
            with self:
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS _litecrate_meta ("
                    "table_name TEXT PRIMARY KEY, "
                    "cache_colums TEXT NOT NULL"
                    ")"
                )
                self._load_cache()

        except BaseException:
            self._conn.close()
            raise

    # region helpers
    def _load_cache(self) -> None:
        self._cache.clear()

        rows = self._conn.execute(
            "SELECT table_name, cache_colums FROM _litecrate_meta"
        )

        for table_name, cache_colums in rows:
            columns: dict[str, type | None] = {}

            for entry in filter(None, cache_colums.split(",")):
                try:
                    name, type_name = entry.rsplit(":", 1)
                    columns[unquote(name)] = self._CACHE_TYPES[type_name]

                except (ValueError, KeyError) as exc:
                    raise ValueError(
                        f"Invalid cache metadata for table {table_name!r}"
                    ) from exc

            self._cache[table_name] = columns

    def _save_cache(self, table_name: str) -> None:
        columns: list[str] = []

        for name, column_type in self._cache[table_name].items():
            type_name = "None" if column_type is None else column_type.__name__

            if (
                type_name not in self._CACHE_TYPES
                or self._CACHE_TYPES[type_name] is not column_type
            ):
                raise TypeError(f"Unsupported cache type: {column_type!r}")

            columns.append(f"{quote(name, safe='')}:{type_name}")

        self._conn.execute(
            "INSERT INTO _litecrate_meta "
            "(table_name, cache_colums) "
            "VALUES (?, ?) "
            "ON CONFLICT(table_name) DO UPDATE SET "
            "cache_colums = excluded.cache_colums",
            (
                table_name,
                ",".join(columns),
            ),
        )

    @staticmethod
    def _dump_json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _json_path(name: str) -> str:
        label = json.dumps(name, ensure_ascii=False)[1:-1].replace(r"\"", r"\u0022")
        return f'$."{label}"'

    @staticmethod
    def _local_subqueries(tokens: list[re.Match[str]]) -> set[int]:
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

    @classmethod
    @lru_cache(maxsize=128)
    def _query_parts(cls, query: str) -> tuple[tuple[int, int, str | int], ...]:
        tokens = [
            token
            for token in cls._QUERY_TOKENS.finditer(query)
            if token.lastgroup != "comment"
        ]
        parts: list[tuple[int, int, str | int]] = []
        last_slot = 0
        named_slots: dict[str, int] = {}
        skip_depth = 0
        upper_query = query.upper()
        local: set[int] = set()
        if "SELECT" in upper_query or "WITH" in upper_query:
            local = cls._local_subqueries(tokens)

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
                if raw.upper() in cls._SQL_WORDS or previous == "NULLS":
                    continue

                name = raw

            elif raw[0] == "[":
                name = raw[1:-1]

            else:
                name = raw[1:-1].replace(raw[0] * 2, raw[0])

            if name.isascii() and "\0" not in name:
                parts.append((*token.span(), normalize_identifier(name)))

        return tuple(parts)

    def _expand_query(self, table_name: str, query: str, bind_offset: int = 0) -> str:
        columns = self._cache.get(table_name)
        if columns is not None and "_data" not in columns:
            columns = None

        if columns is None and not self._SPECIAL_BIND.search(query):
            return query

        result: list[str] = []
        end = 0
        for start, stop, part in self._query_parts(query):
            if isinstance(part, int):
                if part == 0 or (bind_offset == 0 and query[start] == "?"):
                    continue

                replacement = f"?{part + bind_offset}"

            elif columns is not None and part not in columns:
                path = self._json_path(part).replace("'", "''")
                replacement = f"""json_extract("_data", '{path}')"""

            else:
                continue

            result.append(query[end:start])
            result.append(replacement)
            end = stop

        if not result:
            return query

        result.append(query[end:])
        return "".join(result)

    def _prepare_values(
        self,
        table_name: str,
        values: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        columns = self._cache.get(table_name)

        if columns is None:
            raise ValueError(f"Table {table_name!r} is not registered in cache")

        known: dict[str, object] = {}
        extra: dict[str, object] = {}
        flexible = "_data" in columns

        for original_name, value in values.items():
            name = normalize_identifier(original_name)
            check_column_name(name)

            if name in known or name in extra:
                raise ValueError(f"Duplicate column: {name!r}")

            if name in columns:
                column_type = columns[name]

                if (column_type is dict or column_type is list) and value is not None:
                    if not isinstance(value, column_type):
                        raise TypeError(
                            f"Column {name!r} requires {column_type.__name__}, "
                            f"got {type(value).__name__}"
                        )

                    value = self._dump_json(value)

                known[name] = value

            elif flexible:
                extra[name] = value

            else:
                raise KeyError(f"Unknown column {name!r} in table {table_name!r}")

        return known, extra

    def _decode_row(
        self,
        table_name: str,
        row: dict[str, object],
    ) -> dict[str, object]:
        columns = self._cache.get(table_name)
        if columns is None:
            return row

        for name, column_type in columns.items():
            if name == "_data" or name not in row or row[name] is None:
                continue

            if column_type is dict or column_type is list:
                raw_value = row[name]
                if not isinstance(raw_value, (str, bytes, bytearray)):
                    raise TypeError(f"Invalid stored JSON for column {name!r}")

                parsed = json.loads(raw_value)
                if not isinstance(parsed, column_type):
                    raise ValueError(
                        f"Invalid JSON type for column {name!r} in table {table_name!r}"
                    )

                row[name] = parsed

            elif column_type is bool:
                row[name] = bool(row[name])

        if "_data" in columns and "_data" in row:
            raw = row.pop("_data")
            if raw is not None:
                if not isinstance(raw, (str, bytes, bytearray)):
                    raise TypeError(f"Invalid stored _data in table {table_name!r}")

                extra = json.loads(raw)
                if not isinstance(extra, dict):
                    raise ValueError(f"Invalid _data JSON in table {table_name!r}")

                for name, value in extra.items():
                    if name not in row and name not in columns:
                        row[name] = value

        return row

    # endregion

    # region table control
    def create_table(
        self,
        table_name: str,
        *colums: tuple[str | int, str, type | None] | tuple[str | int, str],
        flexible: bool = False,
    ) -> None:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)

        colum_sqls: list[str] = []
        index_sqls: list[str] = []

        if (
            self._conn.execute(
                "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ? COLLATE NOCASE",
                (table_name,),
            ).fetchone()
            is not None
        ):
            return

        column_cache: dict[str, type | None] = {}

        for colum in colums:
            if len(colum) == 2:
                flags, name = colum
                colum_type = None

            else:
                flags, name, colum_type = colum

            check_column_name(name)
            storage_type = (
                str if colum_type is dict or colum_type is list else colum_type
            )
            colum_sql, index_sql = parse_colum_into_sql(
                table_name, flags, name, storage_type
            )

            colum_sqls.append(colum_sql)
            if index_sql:
                index_sqls.append(index_sql)

            column_cache[normalize_identifier(name)] = colum_type

        if flexible:
            colum_sql, _ = parse_colum_into_sql(table_name, 0, "_data", str)
            colum_sqls.append(colum_sql)
            column_cache["_data"] = str

        self._conn.execute(
            f"CREATE TABLE {sanitize_identifier(table_name)} ({', '.join(colum_sqls)})"
        )

        for sql in index_sqls:
            self._conn.execute(sql)

        self._cache[table_name] = column_cache
        self._save_cache(table_name)

    def rename_table(self, target: str, value: str) -> None:
        target, value = normalize_identifiers(target, value)
        check_table_name(target, value)
        san_target, san_value = sanitize_identifiers(target, value)

        indexed_columns = []

        for index_name in self.get_table_indexes(target):
            info = self._conn.execute(
                f"PRAGMA index_info({sanitize_identifier(index_name)})"
            ).fetchall()

            if len(info) != 1:
                continue

            column_name = info[0][2]
            if column_name is None or not column_name.isascii():
                continue

            column_name = normalize_identifier(column_name)
            if index_name == get_index_identifier(target, column_name):
                indexed_columns.append(column_name)

        self._conn.execute(f"ALTER TABLE {san_target} RENAME TO {san_value}")

        for column_name in indexed_columns:
            old_index = get_index_identifier(target, column_name)
            new_index = get_index_identifier(value, column_name)
            san_column = sanitize_identifier(column_name)

            self._conn.execute(f"DROP INDEX {old_index}")
            self._conn.execute(
                f"CREATE INDEX {new_index} ON {san_value} ({san_column})"
            )

        if target in self._cache:
            self._cache[value] = self._cache.pop(target)

        self._conn.execute(
            "UPDATE _litecrate_meta SET table_name = ? WHERE table_name = ?",
            (value, target),
        )

    def get_tables(self, include_internal: bool = False) -> list[str]:
        query = "SELECT name FROM sqlite_schema WHERE type = 'table'"

        if not include_internal:
            query += " AND name NOT GLOB 'sqlite_*' AND name != '_litecrate_meta'"

        query += " ORDER BY name"

        return [row[0] for row in self._conn.execute(query)]

    def delete_table(
        self,
        target: str,
    ) -> None:
        target = normalize_identifier(target)
        check_table_name(target)
        self._conn.execute(f"DROP TABLE IF EXISTS {sanitize_identifier(target)}")
        self._cache.pop(target, None)
        self._conn.execute(
            "DELETE FROM _litecrate_meta WHERE table_name = ?", (target,)
        )

    # endregion

    # region crud
    def insert(
        self,
        table_name: str,
        **values: object,
    ) -> int | None:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        known, extra = self._prepare_values(table_name, values)

        if extra:
            known["_data"] = self._dump_json(extra)

        if not known:
            cursor = self._conn.execute(f"INSERT INTO {san_table} DEFAULT VALUES")
            return cursor.lastrowid

        columns = ", ".join(sanitize_identifier(name) for name in known)
        placeholders = ", ".join("?" for _ in known)

        cursor = self._conn.execute(
            f"INSERT INTO {san_table} ({columns}) VALUES ({placeholders})",
            tuple(known.values()),
        )
        return cursor.lastrowid

    def update(
        self,
        table_name: str,
        query: str,
        *args: object,
        **values: object,
    ) -> int:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        if not query.strip():
            raise ValueError("UPDATE requires a WHERE condition")

        if not values:
            raise ValueError("UPDATE requires at least one value")

        known, extra = self._prepare_values(table_name, values)
        assignments: list[str] = []
        params: list[object] = []

        for name, value in known.items():
            assignments.append(f"{sanitize_identifier(name)} = ?")
            params.append(value)

        if extra:
            data_sql = """COALESCE("_data", '{}')"""
            # json_set takes one document and two arguments per key.
            limit = self._conn.getlimit(sqlite3.SQLITE_LIMIT_FUNCTION_ARG)
            for batch in batched(extra.items(), max(1, (limit - 1) // 2)):
                json_args = ", ".join(["?, json(?)"] * len(batch))
                data_sql = f"json_set({data_sql}, {json_args})"
                for name, value in batch:
                    params.extend((self._json_path(name), self._dump_json(value)))

            assignments.append(f'"_data" = {data_sql}')

        condition = self._expand_query(table_name, query, bind_offset=len(params))
        cursor = self._conn.execute(
            f"UPDATE {san_table} SET {', '.join(assignments)} WHERE {condition}",
            (*params, *args),
        )
        return cursor.rowcount

    def delete(
        self,
        table_name: str,
        query: str,
        *args: object,
    ) -> int:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        if not query.strip():
            raise ValueError("DELETE requires a WHERE condition")

        cursor = self._conn.execute(
            f"DELETE FROM {san_table} WHERE {self._expand_query(table_name, query)}",
            args,
        )
        return cursor.rowcount

    def select(
        self,
        table_name: str,
        query: str = "",
        *args: object,
    ) -> list[dict[str, object]]:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        sql = f"SELECT * FROM {san_table}"
        if query.strip():
            sql += f" WHERE {self._expand_query(table_name, query)}"

        cursor = self._conn.execute(sql, args)
        columns = [column[0] for column in cursor.description]
        return [self._decode_row(table_name, dict(zip(columns, row))) for row in cursor]

    def select_one(
        self,
        table_name: str,
        query: str = "",
        *args: object,
    ) -> dict[str, object] | None:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        sql = f"SELECT * FROM {san_table}"
        if query.strip():
            sql += f" WHERE {self._expand_query(table_name, query)}"

        cursor = self._conn.execute(sql + "\nLIMIT 1", args)
        row = cursor.fetchone()
        if row is None:
            return None

        columns = [column[0] for column in cursor.description]
        return self._decode_row(table_name, dict(zip(columns, row)))

    def count(
        self,
        table_name: str,
        query: str = "",
        *args: object,
    ) -> int:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        sql = f"SELECT COUNT(*) FROM {san_table}"
        if query.strip():
            sql += f" WHERE {self._expand_query(table_name, query)}"

        return self._conn.execute(sql, args).fetchone()[0]

    # endregion

    # region index control
    def get_table_indexes(self, table_name: str) -> list[str]:
        table_name = normalize_identifier(table_name)
        return [
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'index' AND tbl_name = ? COLLATE NOCASE "
                "AND name NOT GLOB 'sqlite_autoindex_*' "
                "ORDER BY name",
                (table_name,),
            )
        ]

    def create_index(self, table_name: str, column_name: str) -> None:
        table_name, column_name = normalize_identifiers(table_name, column_name)
        san_table, san_column = sanitize_identifiers(table_name, column_name)
        # SQLite builds can interpret a double-quoted missing column as text
        # and silently create an index on a constant expression.
        if not any(
            row[1].lower() == column_name
            for row in self._conn.execute(f"PRAGMA table_xinfo({san_table})")
        ):
            raise sqlite3.OperationalError(
                f"No such column {column_name!r} in table {table_name!r}"
            )

        self._conn.execute(
            f"CREATE INDEX {get_index_identifier(table_name, column_name)} ON {san_table} ({san_column})"
        )

    def remove_index(self, table_name: str, column_name: str) -> None:
        table_name, column_name = normalize_identifiers(table_name, column_name)
        self._conn.execute(
            f"DROP INDEX IF EXISTS {get_index_identifier(table_name, column_name)}"
        )

    # endregion

    # region PRAGMA
    def set_auto_vacuum(
        self,
        value: Literal["NONE", "FULL", "INCREMENTAL"],
    ) -> None:
        if value not in ("NONE", "FULL", "INCREMENTAL"):
            raise ValueError(f"Invalid auto_vacuum value: {value!r}")

        self._conn.execute(f"PRAGMA auto_vacuum={value}")

    def set_journal_mode(
        self,
        value: Literal["DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"],
    ) -> None:
        if value not in ("DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"):
            raise ValueError(f"Invalid journal_mode value: {value!r}")

        result = self._conn.execute(f"PRAGMA journal_mode={value}").fetchone()[0]

        if result.upper() != value:
            raise RuntimeError(
                f"Failed to set journal mode to {value!r}, got {result!r}"
            )

    def incremental_vacuum(self, pages: int | None = None) -> None:
        if pages is not None and (type(pages) is not int or pages <= 0):
            raise ValueError("Pages must be a positive integer")

        query = "PRAGMA incremental_vacuum"

        if pages is not None:
            query += f"({pages})"

        # Incremental vacuum requires stepping through the entire statement
        for _ in self._conn.execute(query):
            pass

    # endregion

    def vacuum(self) -> None:
        self._conn.execute("VACUUM")

    def close(self) -> None:
        self._conn.close()

    # region context funcs
    def __enter__(self) -> Self:
        if self._rollback_cache is not None:
            raise RuntimeError("Nested transactions are not supported")

        snapshot = self._cache.copy()
        self._conn.execute("BEGIN")
        self._rollback_cache = snapshot
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        snapshot = self._rollback_cache
        if snapshot is None:
            raise RuntimeError("No active transaction")

        committed = False
        try:
            if exc_type is None:
                self._conn.execute("COMMIT")
                committed = True

        finally:
            self._rollback_cache = None
            if not committed:
                self._cache = snapshot
                self._conn.rollback()

    # endregion

import sqlite3
from copy import deepcopy
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
            check_same_thread=False,
        )

        self._cache: dict[str, dict[str, type | None]] = {}
        self._rollback_cache: dict[str, dict[str, type | None]] | None = None

        with self:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS _litecrate_meta ("
                "table_name TEXT PRIMARY KEY, "
                "cache_colums TEXT NOT NULL"
                ")"
            )
            self._load_cache()

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
                "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?",
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
            colum_sql, index_sql = parse_colum_into_sql(
                table_name, flags, name, colum_type
            )

            colum_sqls.append(colum_sql)
            if index_sql:
                index_sqls.append(index_sql)

            column_cache[normalize_identifier(name)] = colum_type

        if flexible:
            colum_sql, _ = parse_colum_into_sql(table_name, 0, "_data")
            colum_sqls.append(colum_sql)
            column_cache["_data"] = None

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
            if column_name is None:
                continue

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

    # region index control
    def get_table_indexes(self, table_name: str) -> list[str]:
        table_name = normalize_identifier(table_name)
        return [
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'index' AND tbl_name = ? "
                "AND name NOT GLOB 'sqlite_autoindex_*' "
                "ORDER BY name",
                (table_name,),
            )
        ]

    def create_index(self, table_name: str, column_name: str) -> None:
        table_name, column_name = normalize_identifiers(table_name, column_name)
        san_table, san_column = sanitize_identifiers(table_name, column_name)
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

    # endregion

    def vacuum(self) -> None:
        self._conn.execute("VACUUM")

    def close(self) -> None:
        self._conn.close()

    # region context funcs
    def __enter__(self) -> Self:
        if self._rollback_cache is not None:
            raise RuntimeError("Nested transactions are not supported")

        self._conn.execute("BEGIN")
        self._rollback_cache = deepcopy(self._cache)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self._conn.execute("COMMIT")

        else:
            self._conn.execute("ROLLBACK")
            self._cache = self._rollback_cache  # pyright: ignore[reportAttributeAccessIssue] | Никогда не None

        self._rollback_cache = None

    # endregion


# сделать insert
# сделать update
# сделать delete
# сделать select
# сделать count
# сделать select_one

# работа с json (во всвяком случае поддержка json)?
# кеша немного наверное чтобы понимать куда можем пихнуть произвольный json?

# Сохранение и загрузка кеша из бд. Сейчас кеш бесмысленный ибо умирает как только умирает бд.

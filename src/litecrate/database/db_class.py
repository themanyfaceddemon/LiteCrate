import json
import sqlite3
from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
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
from ..utils.sql import (
    JSON_ENCODER,
    build_insert_sql,
    json_field_expression,
    json_path,
    rewrite_where,
)


class Database:
    """A lightweight SQLite interface with typed columns and flexible JSON fields.

    Schema metadata is stored in the database, and transactions are managed
    explicitly using ``with db:``.
    """

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
        """Open a SQLite database and load LiteCrate schema metadata.

        Args:
            db_path: Database file path, or ``":memory:"`` for an in-memory database.
            timeout: Seconds to wait when the database is locked.

        The connection uses autocommit outside explicit transactions. Access
        from multiple threads requires external synchronization.
        """

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
        """Restore declared column types from the internal metadata table."""

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

    def _save_table_metadata(
        self,
        table_name: str,
        column_types: dict[str, type | None],
    ) -> None:
        """Write a table's declared column types to the SQLite metadata table."""

        columns: list[str] = []

        for name, column_type in column_types.items():
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

    @contextmanager
    def _schema_transaction(self) -> Generator[None]:
        """Apply a schema change, its indexes, and its metadata as one operation.

        For example, a failed CREATE INDEX rolls back the preceding CREATE
        TABLE. A savepoint also lets the caller catch that error inside
        ``with db`` and continue the transaction.
        """

        connection = self._conn
        inside_transaction = connection.in_transaction
        connection.execute("SAVEPOINT _litecrate_schema")
        try:
            yield
            connection.execute("RELEASE _litecrate_schema")

        except BaseException:
            if connection.in_transaction:
                if inside_transaction:
                    connection.execute("ROLLBACK TO _litecrate_schema")
                    connection.execute("RELEASE _litecrate_schema")

                else:
                    connection.rollback()

            raise

    def _expand_query(self, table_name: str, query: str, bind_offset: int = 0) -> str:
        columns = self._cache.get(table_name)
        if columns is not None and "_data" not in columns:
            columns = None

        return rewrite_where(query, columns, bind_offset)

    def _prepare_values(
        self,
        table_name: str,
        values: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Validate input fields and separate declared columns from JSON extras.

        Declared ``dict`` and ``list`` values are serialized for SQLite.
        Unknown fields are accepted only for tables with flexible storage.
        """

        columns = self._cache.get(table_name)

        if columns is None:
            raise ValueError(f"Table {table_name!r} is not registered in cache")

        known: dict[str, object] = {}
        extra: dict[str, object] = {}
        flexible = "_data" in columns

        for original_name, value in values.items():
            name = normalize_identifier(original_name)
            if name == "_data":
                raise ValueError("Column name '_data' is reserved")

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

                    value = JSON_ENCODER.encode(value)

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
        columns: dict[str, type | None],
        typed_columns: Iterable[tuple[str, type | None]],
    ) -> dict[str, object]:
        """Restore typed values and merge flexible JSON fields into a result row.

        The internal ``_data`` column is omitted from the returned dictionary.
        """

        for name, column_type in typed_columns:
            if name == "_data":
                continue

            if column_type is bool:
                value = row.get(name)
                if value is not None:
                    row[name] = bool(value)

            elif column_type is dict or column_type is list:
                raw_value = row.get(name)
                if raw_value is None:
                    continue

                if not isinstance(raw_value, (str, bytes, bytearray)):
                    raise TypeError(f"Invalid stored JSON for column {name!r}")

                parsed = json.loads(raw_value)
                if not isinstance(parsed, column_type):
                    raise ValueError(
                        f"Invalid JSON type for column {name!r} in table {table_name!r}"
                    )

                row[name] = parsed

        if "_data" in columns:
            raw = row.pop("_data", None)
            if raw is not None:
                if not isinstance(raw, (str, bytes, bytearray)):
                    raise TypeError(f"Invalid stored _data in table {table_name!r}")

                extra = json.loads(raw)
                if not isinstance(extra, dict):
                    raise ValueError(f"Invalid _data JSON in table {table_name!r}")

                for name, value in extra.items():
                    if name not in columns:
                        row.setdefault(name, value)

        return row

    # endregion

    # region table control
    def create_table(
        self,
        table_name: str,
        *colums: tuple[str | int, str, type | None] | tuple[str | int, str],
        flexible: bool = False,
    ) -> None:
        """Create a table from column definitions if it does not already exist.

        Args:
            table_name: Name of the table to create.
            *colums: ``(flags, name)`` or ``(flags, name, python_type)`` tuples.
            flexible: Store undeclared fields in the internal JSON column.

        Existing tables are left untouched, even if their definitions differ.
        The flags are interpreted by ``parse_colum_into_sql``.
        """

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

        san_table = sanitize_identifier(table_name)
        with self._schema_transaction():
            self._conn.execute(f"CREATE TABLE {san_table} ({', '.join(colum_sqls)})")
            for sql in index_sqls:
                self._conn.execute(sql)

            self._save_table_metadata(table_name, column_cache)

        self._cache[table_name] = column_cache

    def rename_table(self, target: str, value: str) -> None:
        """Rename a table, its metadata, and LiteCrate-generated indexes.

        Args:
            target: Current table name.
            value: New table name.
        """

        target, value = normalize_identifiers(target, value)
        check_table_name(target, value)
        san_target, san_value = sanitize_identifiers(target, value)

        with self._schema_transaction():
            indexes = list(self._managed_indexes(target, san_target))
            self._conn.execute(f"ALTER TABLE {san_target} RENAME TO {san_value}")

            for index_name, column_name, expression in indexes:
                new_index = get_index_identifier(value, column_name)
                self._conn.execute(f"DROP INDEX {index_name}")
                self._conn.execute(
                    f"CREATE INDEX {new_index} ON {san_value} ({expression})"
                )

            self._conn.execute(
                "UPDATE _litecrate_meta SET table_name = ? WHERE table_name = ?",
                (value, target),
            )

        if target in self._cache:
            self._cache[value] = self._cache.pop(target)

    def _managed_indexes(
        self,
        table_name: str,
        san_table: str,
    ) -> Iterator[tuple[str, str, str]]:
        indexes = self._conn.execute(
            "SELECT name, sql FROM sqlite_schema "
            "WHERE type = 'index' AND tbl_name = ? COLLATE NOCASE "
            "AND name GLOB 'idx_*' AND sql IS NOT NULL",
            (table_name,),
        )
        for index_name, sql in indexes:
            info = self._conn.execute(
                f"PRAGMA index_info({sanitize_identifier(index_name)})"
            ).fetchall()
            if len(info) != 1:
                continue

            column_name = info[0][2]
            if column_name is None:
                # SQLite reports NULL for expression indexes. Recover the field
                # from the exact SQL emitted by create_index().
                prefix = f"""CREATE INDEX {index_name} ON {san_table} (json_extract("_data", '$."""
                suffix = "'))"
                if not sql.startswith(prefix) or not sql.endswith(suffix):
                    continue

                try:
                    label = sql.removeprefix(prefix).removesuffix(suffix)
                    column_name = json.loads(label.replace("''", "'"))

                except json.JSONDecodeError:
                    continue
                if (
                    not isinstance(column_name, str)
                    or not column_name.isascii()
                    or "\0" in column_name
                ):
                    continue

                expression = json_field_expression(column_name)

                if sql != f"CREATE INDEX {index_name} ON {san_table} ({expression})":
                    continue

            else:
                if not column_name.isascii():
                    continue

                column_name = normalize_identifier(column_name)
                expression = sanitize_identifier(column_name)

            if index_name == get_index_identifier(table_name, column_name):
                yield index_name, column_name, expression

    def get_tables(self, include_internal: bool = False) -> list[str]:
        """Return sorted table names, optionally including SQLite internal tables.

        Args:
            include_internal: Include ``sqlite_*`` and LiteCrate metadata tables.
        """

        query = "SELECT name FROM sqlite_schema WHERE type = 'table'"

        if not include_internal:
            query += " AND name NOT GLOB 'sqlite_*' AND name != '_litecrate_meta'"

        query += " ORDER BY name"

        return [row[0] for row in self._conn.execute(query)]

    def delete_table(
        self,
        target: str,
    ) -> None:
        """Drop a table and its cached metadata if present."""

        target = normalize_identifier(target)
        check_table_name(target)
        san_target = sanitize_identifier(target)
        with self._schema_transaction():
            self._conn.execute(f"DROP TABLE IF EXISTS {san_target}")
            self._conn.execute(
                "DELETE FROM _litecrate_meta WHERE table_name = ?", (target,)
            )

        self._cache.pop(target, None)

    # endregion

    # region crud
    def insert(
        self,
        table_name: str,
        **values: object,
    ) -> int | None:
        """Insert a row using keyword arguments for its field values.

        Undeclared fields are accepted only in flexible tables and stored as
        JSON. An empty ``values`` mapping inserts a row of default values.

        Returns:
            The SQLite ``lastrowid``, or ``None`` if unavailable.
        """

        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        known, extra = self._prepare_values(table_name, values)
        if extra:
            known["_data"] = JSON_ENCODER.encode(extra)

        sql = build_insert_sql(table_name, tuple(known))
        return self._conn.execute(sql, tuple(known.values())).lastrowid

    def update(
        self,
        table_name: str,
        query: str,
        *args: object,
        **values: object,
    ) -> int:
        """Update matching rows with the supplied field values.

        Args:
            table_name: Table to modify.
            query: SQL condition without ``WHERE``; must not be empty.
            *args: Values bound to placeholders in ``query``.
            **values: Fields to update; at least one is required.

        Flexible JSON keys are updated individually. A new dictionary or list
        replaces the complete value of that field, not its nested contents.

        Returns:
            Number of affected rows.
        """

        if not query.strip():
            raise ValueError("UPDATE requires a WHERE condition")

        return self._update(table_name, query, args, values)

    def update_all(self, table_name: str, **values: object) -> int:
        """Update the supplied fields in every row and return the affected count."""

        return self._update(table_name, None, (), values)

    def _update(
        self,
        table_name: str,
        query: str | None,
        args: tuple[object, ...],
        values: dict[str, object],
    ) -> int:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        if not values:
            raise ValueError("UPDATE requires at least one value")

        known, extra = self._prepare_values(table_name, values)
        assignments = [f"{sanitize_identifier(name)} = ?" for name in known]
        params = list(known.values())

        if extra:
            data_sql = """COALESCE("_data", '{}')"""
            # json_set takes one document and two arguments per key.
            limit = self._conn.getlimit(sqlite3.SQLITE_LIMIT_FUNCTION_ARG)
            for batch in batched(extra.items(), max(1, (limit - 1) // 2)):
                json_args = ", ".join(["?, json(?)"] * len(batch))
                data_sql = f"json_set({data_sql}, {json_args})"
                for name, value in batch:
                    params.extend((json_path(name), JSON_ENCODER.encode(value)))

            assignments.append(f'"_data" = {data_sql}')

        sql = f"UPDATE {san_table} SET {', '.join(assignments)}"
        if query is not None:
            condition = self._expand_query(table_name, query, bind_offset=len(params))
            sql += f" WHERE {condition}"

        cursor = self._conn.execute(sql, (*params, *args))
        return cursor.rowcount

    def delete(
        self,
        table_name: str,
        query: str,
        *args: object,
    ) -> int:
        """Delete rows matching a non-empty SQL condition.

        Args:
            table_name: Table to modify.
            query: SQL condition without ``WHERE``; must not be empty.
            *args: Values bound to placeholders in ``query``.

        Returns:
            Number of deleted rows.
        """

        if not query.strip():
            raise ValueError("DELETE requires a WHERE condition")

        return self._delete(table_name, query, args)

    def delete_all(self, table_name: str) -> int:
        """Delete every row in the table and return the number of deleted rows."""

        return self._delete(table_name, None, ())

    def _delete(
        self, table_name: str, query: str | None, args: tuple[object, ...]
    ) -> int:
        table_name = normalize_identifier(table_name)
        check_table_name(table_name)

        sql = f"DELETE FROM {sanitize_identifier(table_name)}"
        if query is not None:
            sql += f" WHERE {self._expand_query(table_name, query)}"

        cursor = self._conn.execute(sql, args)
        return cursor.rowcount

    def select(
        self,
        table_name: str,
        query: str = "",
        *args: object,
    ) -> list[dict[str, object]]:
        """Return all rows matching an optional SQL condition.

        Args:
            table_name: Table to read.
            query: SQL condition without ``WHERE``; empty means all rows.
            *args: Values bound to placeholders in ``query``.

        Declared types and flexible JSON fields are restored in each result.

        Returns:
            A list of row dictionaries, or an empty list if none match.
        """

        table_name = normalize_identifier(table_name)
        check_table_name(table_name)
        san_table = sanitize_identifier(table_name)

        sql = f"SELECT * FROM {san_table}"
        if query.strip():
            sql += f" WHERE {self._expand_query(table_name, query)}"

        cursor = self._conn.execute(sql, args)
        columns = [column[0] for column in cursor.description]
        declared = self._cache.get(table_name, {})
        typed_columns = tuple(
            (name, column_type)
            for name, column_type in declared.items()
            if name != "_data" and column_type in (dict, list, bool)
        )
        if not typed_columns and "_data" not in declared:
            return [dict(zip(columns, row)) for row in cursor]

        return [
            self._decode_row(
                table_name, dict(zip(columns, row)), declared, typed_columns
            )
            for row in cursor
        ]

    def select_one(
        self,
        table_name: str,
        query: str = "",
        *args: object,
    ) -> dict[str, object] | None:
        """Return one matching row as a dictionary, or ``None`` if absent.

        The optional ``query`` and ``args`` work as in ``select``. Without an
        ordering guarantee, any one of multiple matching rows may be returned.
        """

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
        result = dict(zip(columns, row))
        declared = self._cache.get(table_name)
        if declared is not None:
            return self._decode_row(table_name, result, declared, declared.items())

        return result

    def count(
        self,
        table_name: str,
        query: str = "",
        *args: object,
    ) -> int:
        """Count rows matching an optional SQL condition.

        Args:
            table_name: Table to read.
            query: SQL condition without ``WHERE``; empty means all rows.
            *args: Values bound to placeholders in ``query``.

        Returns:
            Number of matching rows.
        """

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
        """Return sorted index names, excluding SQLite's automatic indexes."""

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

    def create_index(
        self,
        table_name: str,
        column_name: str,
        *,
        flexible: bool = False,
    ) -> None:
        """Create a named index on a declared column or a flexible field.

        Pass ``flexible=True`` to index an undeclared JSON field in a flexible
        table. SQLite raises an error if the generated name is already in use.
        """

        table_name, column_name = normalize_identifiers(table_name, column_name)
        san_table = sanitize_identifier(table_name)
        if flexible:
            check_column_name(column_name)
            columns = self._cache.get(table_name, {})
            if "_data" not in columns:
                raise ValueError(f"Table {table_name!r} has no flexible fields")

            if column_name in columns:
                raise ValueError(
                    f"Column {column_name!r} is declared in table {table_name!r}"
                )

            expression = json_field_expression(column_name)

        else:
            # SQLite can treat a double-quoted missing column as a string.
            if not any(
                row[1].lower() == column_name
                for row in self._conn.execute(f"PRAGMA table_xinfo({san_table})")
            ):
                raise sqlite3.OperationalError(
                    f"No such column {column_name!r} in table {table_name!r}"
                )

            expression = sanitize_identifier(column_name)

        self._conn.execute(
            f"CREATE INDEX {get_index_identifier(table_name, column_name)} ON {san_table} ({expression})"
        )

    def remove_index(self, table_name: str, column_name: str) -> None:
        """Drop the LiteCrate-named index for a column if it exists."""

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
        """Set SQLite's ``auto_vacuum`` mode.

        Accepted values are ``NONE``, ``FULL``, and ``INCREMENTAL``. Changing
        an existing database between ``NONE`` and another mode requires
        a subsequent ``vacuum()`` to take effect.
        """

        if value not in ("NONE", "FULL", "INCREMENTAL"):
            raise ValueError(f"Invalid auto_vacuum value: {value!r}")

        self._conn.execute(f"PRAGMA auto_vacuum={value}")

    def set_journal_mode(
        self,
        value: Literal["DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"],
    ) -> None:
        """Set SQLite's journal mode and verify the selected mode took effect.

        Raises:
            ValueError: If the mode name is unsupported.
            RuntimeError: If SQLite reports a different journal mode.
        """

        if value not in ("DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"):
            raise ValueError(f"Invalid journal_mode value: {value!r}")

        result = self._conn.execute(f"PRAGMA journal_mode={value}").fetchone()[0]

        if result.upper() != value:
            raise RuntimeError(
                f"Failed to set journal mode to {value!r}, got {result!r}"
            )

    def incremental_vacuum(self, pages: int | None = None) -> None:
        """Reclaim free pages when SQLite uses incremental auto-vacuum.

        Args:
            pages: Maximum pages to reclaim; ``None`` requests all available
                pages. A positive integer is required when specified.

        This operation has no effect unless ``auto_vacuum`` is ``INCREMENTAL``.
        """

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
        """Rebuild the database using SQLite's ``VACUUM`` command.

        This cannot run inside an active transaction.
        """

        self._conn.execute("VACUUM")

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._conn.close()

    # region context funcs
    def __enter__(self) -> Self:
        """Begin a transaction and snapshot the schema cache for rollback.

        Returns:
            This database instance.

        Raises:
            RuntimeError: If a transaction is already active.
        """

        if self._rollback_cache is not None:
            raise RuntimeError("Nested transactions are not supported")

        # fuking magic
        snapshot = {table: columns.copy() for table, columns in self._cache.items()}
        self._conn.execute("BEGIN")
        self._rollback_cache = snapshot
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit on success, or roll back SQL and cached schema changes.

        A failed commit also triggers rollback. Exceptions are propagated to
        the caller rather than suppressed.
        """

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

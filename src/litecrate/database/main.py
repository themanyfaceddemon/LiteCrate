import sqlite3
from copy import deepcopy
from hashlib import blake2s
from pathlib import Path
from types import TracebackType
from typing import Literal, Self

from ..utils import INDEX_BIT, NOT_NULL_BIT, PRIMARY_BIT, UNIQUE_BIT, parse_column
from ..utils import sanitize_identifier as san


class Database:
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

        self._cache: dict = {}
        self._rollback_cache: dict | None = None

    # region helpers
    @staticmethod
    def _get_colums_sql_create(
        colum: str,
        table_name: str,
        san_table_name: str,
    ) -> tuple[str, str | None]:
        return_index = None

        bits, colum_name, colum_type = parse_column(colum)
        san_colum_name = san(colum_name)
        return_sql = f"{san_colum_name} {colum_type or ''}".rstrip()

        if bits & INDEX_BIT and not (bits & (PRIMARY_BIT | UNIQUE_BIT)):
            raw = f"{table_name}\0{colum_name}".encode()
            index_name = f"idx_{blake2s(raw, digest_size=16).hexdigest()}"

            return_index = (
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                f"ON {san_table_name} ({san_colum_name})"
            )

        if bits & PRIMARY_BIT:
            return_sql += " PRIMARY KEY"

        if bits & NOT_NULL_BIT:
            return_sql += " NOT NULL"

        if bits & UNIQUE_BIT:
            return_sql += " UNIQUE"

        return return_sql, return_index

    # endregion

    # region table control
    def create_table(
        self,
        table_name: str,
        *colums: str,
        flexible: bool = False,
    ) -> None:
        index_l = []
        colums_l = []

        san_table_name = san(table_name)

        if flexible:
            colums_l.append("_data TEXT")

        for colum in colums:
            tmp_sql, tmp_index = self._get_colums_sql_create(
                colum,
                table_name,
                san_table_name,
            )
            if tmp_index is not None:
                index_l.append(tmp_index)

            colums_l.append(tmp_sql)

        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {san_table_name} ({', '.join(colums_l)})"
        )
        for index in index_l:
            self._conn.execute(index)

    def rename_table(
        self,
        target: str,
        value: str,
    ) -> None:
        self._conn.execute(f"ALTER TABLE {san(target)} RENAME TO {san(value)}")

        if target in self._cache:
            self._cache[value] = self._cache.pop(target)

    def get_tables(self, include_internal: bool = False) -> list[str]:
        query = "SELECT name FROM sqlite_schema WHERE type = 'table'"

        if not include_internal:
            query += " AND name NOT GLOB 'sqlite_*'"

        query += " ORDER BY name"

        return [row[0] for row in self._conn.execute(query)]

    def delete_table(
        self,
        target: str,
    ) -> None:
        self._conn.execute(f"DROP TABLE IF EXISTS {san(target)}")

        self._cache.pop(target, None)

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


# сделать create_table

# сделать insert
# сделать update
# сделать delete
# сделать select
# сделать count
# сделать select_one

# работа с json (во всвяком случае поддержка json)?
# кеша немного наверное чтобы понимать куда можем пихнуть произвольный json?

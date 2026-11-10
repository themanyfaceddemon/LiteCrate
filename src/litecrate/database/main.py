import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Literal, Self


class Database:
    def __init__(self, db_path: Path | str, timeout: float = 30.0) -> None:
        self._conn = sqlite3.connect(
            str(db_path),
            timeout=timeout,
            isolation_level=None,
            check_same_thread=False,
        )

    # region PRAGMA
    def set_auto_vacuum(self, value: Literal["NONE", "FULL", "INCREMENTAL"]) -> None:
        if value not in ("NONE", "FULL", "INCREMENTAL"):
            raise ValueError(f"Invalid auto_vacuum value: {value!r}")

        self._conn.execute(f"PRAGMA auto_vacuum={value}")

    def set_journal_mode(
        self,
        value: Literal["DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"],
    ) -> None:
        if value not in ("DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"):
            raise ValueError(f"Invalid journal_mod value: {value!r}")

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

    def __enter__(self) -> Self:
        self._conn.execute("BEGIN")
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


# TODO: бога убить
# сделать create_table
# сделать delete_table
# сделать insert
# жену выгулять (у меня её нет, шизойд)
# сделать update
# сделать delete
# сделать select
# сделать count
# сделать select_one
# сделать get_tables
# сделать rename_table
# работа с json (во всвяком случае поддержка json)
# кеша немного наверное чтобы понимать куда можем пихнуть произвольный json?

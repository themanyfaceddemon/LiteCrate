# LiteCrate

[Documentation](https://themanyfaceddemon.github.io/LiteCrate/)

LiteCrate is a small Python library for working with SQLite. It lets you create tables, insert and update records using keyword arguments, and search using SQL conditions.

If records have different sets of fields, additional values can be stored as JSON without changing the table schema.

## Installation

LiteCrate requires Python 3.13 or newer. No third-party dependencies are required to use the library.

```bash
python -m pip install litecrate
```

## Your first table

```python
from litecrate import Database

db = Database(":memory:")

with db:
    db.create_table(
        "players",
        ("p", "id", int),
        ("un", "login", str),
        (0, "level", int),
    )

    player_id = db.insert("players", login="ada", level=3)
    db.update("players", "id = ?", player_id, level=4)

print(db.select_one("players", "login = ?", "ada"))
# {'id': 1, 'login': 'ada', 'level': 4}

db.close()
```

Here, `create_table()` creates a table with three columns. The `p` flag defines a primary key, while `un` defines a required, unique value. `insert()` adds a row, `update()` changes it using a condition, and `select_one()` returns the matching row as a dictionary.

`with db:` groups operations into a transaction: changes are committed if the block completes successfully and rolled back if an exception occurs. The block **does not close** the connection; call `db.close()` to close it.

## Storing data in a file

The example uses `":memory:"` - an in-memory database that disappears when the connection is closed. To preserve data between runs, pass a file path:

```python
db = Database("players.sqlite3")
```

If the file does not exist, SQLite creates it automatically.

## License

LiteCrate is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See the [LICENCE](./LICENSE) file for the full license text.

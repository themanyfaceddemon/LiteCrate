---
layout: default
title: Tables and data types
lang: en
---

# Tables and data types

[Home](index.md) · [Русский](../rus/tables.md)

## Creating tables

Use `create_table(table_name, *colums, flexible=False)` to create a table.

```python
db.create_table(
    "players",
    ("p", "id", int),
    ("un", "login", str),
    ("i", "level", int),
)
```

Each column is specified as a tuple `(flags, name, type)`: its flags, name, and Python type. The type can be omitted; in that case, the column has no declared SQLite type.

```python
db.create_table("events", (0, "payload"))
```

**Important:** if a table with the given name already exists, `create_table()` makes no changes. New columns, types, constraints, and indexes in the updated definition **are not applied**. This method does not perform schema migrations.

## Column flags

Flags can be supplied as a string in any order and case. Use `0` or `""` for a column without flags.

| Flag | Effect |
|---|---|
| `i` | Create an index on the column. |
| `n` | Disallow `NULL` (`NOT NULL`). |
| `p` | Make the column a primary key (`PRIMARY KEY`). |
| `u` | Add a uniqueness constraint (`UNIQUE`). |

For example, `("un", "login", str)` defines a required, unique login.

When creating a table, LiteCrate does not create a separate `i` index if the same column is already marked with `u` or `p`. See [Indexes](indexes.md).

**SQLite detail:** in an ordinary table, a non-integer primary key does not always prohibit `NULL`. If the value is required, explicitly add `n`, for example `("pn", "code", str)`. An integer `("p", "id", int)` is used as an `INTEGER PRIMARY KEY`, for which SQLite can assign an identifier automatically.

## Data types

| Python type | SQLite type |
|---|---|
| `int`, `bool` | `INTEGER` |
| `float` | `REAL` |
| `str` | `TEXT` |
| `bytes` | `BLOB` |
| `dict`, `list` | `TEXT` (JSON) |
| `None` or an omitted type | No declared type |

`dict` and `list` columns are automatically converted to JSON on write and restored on read. `bool` columns return `True` or `False`. Other types follow SQLite's type conversion rules.

If there is no `NOT NULL` constraint, you can pass `None`, including for `dict` and `list` columns.

## Managing tables

| Method | Effect |
|---|---|
| `get_tables(include_internal=False)` | Return table names in alphabetical order. |
| `rename_table(target, value)` | Rename a table. |
| `delete_table(target)` | Drop a table if it exists. |

```python
db.rename_table("players", "members")
print(db.get_tables())
# ['members']

db.delete_table("members")
```

By default, `get_tables()` hides internal tables; `include_internal=True` includes them in the result. When renaming a table, LiteCrate also moves its metadata and renames indexes created using its naming scheme.

## Metadata

LiteCrate stores declared column type information in the internal `_litecrate_meta` table. This allows `bool`, `dict`, and `list` values to be read correctly after reopening the database.

The name `_litecrate_meta` is reserved for the metadata table. The `_data` column is used for [flexible fields](flexible.md) and is also reserved.

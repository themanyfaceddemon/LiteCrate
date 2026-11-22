---
layout: default
title: Working with records
lang: en
---

# Working with records

[Home](index.md) · [Русский](../rus/records.md)

## Inserting records

`insert(table_name, **values)` inserts a record. Pass field values as keyword arguments.

```python
player_id = db.insert("players", login="ada", level=3)
```

The method returns `lastrowid` - the identifier of the last inserted row (`int` or `None`). If no fields are supplied, it inserts a row using default values.

## Reading records

| Method | Result |
|---|---|
| `select(table_name, query="", *args)` | A list of dictionaries; `[]` if there are no matches. |
| `select_one(table_name, query="", *args)` | One matching record as a dictionary, or `None`. |
| `count(table_name, query="", *args)` | The number of matching records (`int`). |

```python
players = db.select("players")
player = db.select_one("players", "login = ?", "ada")
total = db.count("players", "level >= ?", 5)
```

Without a condition, read methods operate on all rows in the table. To retrieve a specific record, use a condition on a primary key or unique field: without an explicit order, SQL does not guarantee which of several matching rows will be returned first.

### Search conditions

Pass an SQL expression in `query` **without** the `WHERE` keyword, followed by positional arguments for the `?` placeholders.

```python
db.select("players", "level BETWEEN ? AND ?", 3, 10)
db.select_one("players", "login = ? AND level >= ?", "ada", 5)
```

Do not insert user-supplied values directly into an SQL string; pass them through `?` parameters. The SQL condition itself must come from trusted code.

In [flexible tables](flexible.md), names of additional top-level fields are automatically translated into JSON lookups.

## Updating records

`update(table_name, query, *args, **values)` changes the specified fields in matching records.

```python
changed = db.update("players", "login = ?", "ada", level=10)
```

The method returns the number of affected rows, or `0` if no rows match. You must provide at least one new value and a non-empty condition.

## Deleting records

`delete(table_name, query, *args)` deletes matching rows and returns their number.

```python
removed = db.delete("players", "login = ?", "ada")
```

A condition is required. To explicitly update or delete **all** rows, you can pass the expression `"1"`:

```python
db.update("players", "1", level=0)
db.delete("players", "1")
```

## Errors and limitations

Writing to an unknown column in a regular table raises `KeyError`. In a table with `flexible=True`, additional fields are stored as JSON - see [Flexible fields](flexible.md).

SQLite constraints (`UNIQUE`, `NOT NULL`, `PRIMARY KEY`, and others) still apply. For example, violating a uniqueness constraint raises `sqlite3.IntegrityError`.

If several records must be changed as a single unit, use a [transaction](transactions.md).

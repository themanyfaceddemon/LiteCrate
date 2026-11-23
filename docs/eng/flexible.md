---
layout: default
title: Flexible fields and JSON
lang: en
---

# Flexible fields and JSON

[Home](index.md) · [Русский](../rus/flexible.md)

Flexible tables allow records to have arbitrary sets of fields without changing the table structure.

## Creating a flexible table

Enable flexible fields by passing `flexible=True`:

```python
db.create_table(
    "players",
    ("un", "login", str),
    flexible=True,
)
```

Declared fields are stored in regular SQLite columns, while additional fields are stored as JSON in the internal `_data` column.

## Working with flexible fields

Inserting and reading flexible fields works just like using regular columns.

```python
db.insert(
    "players",
    login="ada",
    level=5,
    settings={"theme": "dark", "sound": True},
)

player = db.select_one("players", "login = ?", "ada")
print(player)
# {
#     'login': 'ada',
#     'level': 5,
#     'settings': {'theme': 'dark', 'sound': True}
# }
```

LiteCrate automatically combines values from regular columns and JSON. The internal `_data` column is not included in the result.

### Updating fields

The `update()` method can change existing fields and add new ones without affecting the other values in a record.

However, dictionaries and lists are **replaced entirely**, rather than merged with their previous contents.

```python
db.update(
    "players",
    "login = ?",
    "ada",
    level=10,
    nickname="Pilot",
    settings={"theme": "light"},
)

player = db.select_one("players", "login = ?", "ada")
print(player)
# {
#     'login': 'ada',
#     'level': 10,
#     'settings': {'theme': 'light'},
#     'nickname': 'Pilot'
# }
```

In this example, `nickname` was added, `level` was updated, and the `settings` dictionary was replaced entirely. As a result, the previous `sound` key is gone.

### Unknown fields

In flexible mode, additional fields are created automatically. This also applies to misspelled names.

```python
db.update("players", "login = ?", "ada", levle=20)

player = db.select_one("players", "login = ?", "ada")

print(player["level"])
# 10

print(player["levle"])
# 20
```

The typo `levle` did not raise an exception: instead of changing `level`, the library created a new field.

## Searching flexible fields

LiteCrate lets you use ordinary SQL conditions to search additional fields.

```python
db.select("players", "level >= ?", 5)
db.count("players", "nickname IS NOT NULL")
```

The library automatically determines which fields are regular columns and which are stored in JSON.

### Nested values

To search inside nested JSON objects, you can use SQLite's `json_extract()` function:

```python
db.select(
    "players",
    "json_extract(_data, '$.settings.theme') = ?",
    "light",
)
```

However, direct access to `_data` is not recommended because it ties your code to LiteCrate's internal storage structure.

## Data types and limitations

Additional fields support JSON-compatible values: strings, finite numbers, `bool`, `None`, lists, and dictionaries with string keys.

Keep these details in mind when working with flexible fields:

- **`None` and missing fields.** `None` is stored as JSON `null`. Missing fields are not included in the returned dictionary. A `field IS NULL` condition may match both cases.
- **Indexes and constraints.** An extra top-level field can have an [index](indexes.md#flexible-field-indexes). Use regular columns for `UNIQUE` and `NOT NULL` constraints.
- **Binary data.** The `bytes` type is not supported in JSON. Use a separate column for binary data.

For more on declaring columns, see [Tables and data types](tables.md).

---
layout: default
title: Utilities
lang: en
---

# Utilities

[Home](index.md) · [Русский](../rus/utils.md)

**Warning! Internal API**

The `litecrate.utils` module is primarily intended for internal use by the library and **is not part of LiteCrate's public API**.

Its functions can be imported directly, but backward compatibility is not guaranteed. Their signatures, behavior, and names may change, or the functions may be removed, without prior notice, including in updates that do not change the major version number.

Use these functions in third-party code at your own risk.

## Table and column names

| Function | Purpose |
|---|---|
| `normalize_identifier(identifier)` | Validate a name and convert it to lowercase. |
| `normalize_identifiers(*identifiers)` | Do the same for multiple names; return a tuple. |
| `sanitize_identifier(identifier)` | Escape a name using double SQL quotes. |
| `sanitize_identifiers(*identifiers)` | Do the same for multiple names; return a tuple. |
| `check_table_name(*names)` | Check that a name is not reserved for the metadata table. |
| `check_column_name(*names)` | Check that a name is not reserved for flexible data. |

Normalization accepts only ASCII names without null characters. The name `_litecrate_meta` is reserved for the internal table, while `_data` is reserved for the internal column.

```python
from litecrate.utils import normalize_identifier, sanitize_identifier

name = normalize_identifier('Display"Name')
print(sanitize_identifier(name))
# "display""name"
```

Escaping identifiers does not replace parameterization of **values**: use `?` for values in SQL queries.

## Schema generation

| Function or type | Purpose |
|---|---|
| `ColumBitEnum` | An `IntFlag` with `INDEX`, `NOT_NULL`, `PRIMARY`, `UNIQUE`, and `AUTOINCREMENT` values. |
| `ColumBitEnum.all_flags()` | Return the combined flag mask. |
| `get_index_identifier(table, colum)` | Generate an index name for a table/column pair. |
| `parse_colum_into_sql(table_name, flags, colum_name, colum_type=None)` | Return `(column_sql, index_sql)`; the second item is `None` if no separate index is needed. |

```python
from litecrate.utils import ColumBitEnum, parse_colum_into_sql

flags = ColumBitEnum.INDEX | ColumBitEnum.NOT_NULL
column_sql, index_sql = parse_colum_into_sql(
    "players", flags, "level", int
)
```

The spellings `ColumBitEnum`, `colum`, and `parse_colum_into_sql` are preserved exactly as used in the API.

Use `Database.create_table()` for `dict` and `list` columns: it stores type information so JSON values can be restored later. See [Tables and data types](tables.md).

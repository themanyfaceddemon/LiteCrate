---
layout: default
title: Settings and maintenance
lang: en
---

# Settings and maintenance

[Home](index.md) · [Русский](../rus/settings.md)

LiteCrate provides methods for configuring SQLite and maintaining the database.

## Journaling

The `set_journal_mode(value)` method sets the SQLite journal mode.

```python
db.set_journal_mode("WAL")
```

Supported values: `DELETE`, `TRUNCATE`, `PERSIST`, `MEMORY`, `WAL`, `OFF`.

If SQLite cannot set the selected mode, the method raises `RuntimeError`.

## Automatic space reclamation

The `set_auto_vacuum(value)` method controls how unused database pages are reclaimed.

| Value | Behavior |
|---|---|
| `NONE` | Automatic space reclamation is disabled. |
| `FULL` | Reclaim unused pages when transactions are committed. |
| `INCREMENTAL` | Allow pages to be reclaimed manually, without automatic cleanup. |

```python
db.set_auto_vacuum("INCREMENTAL")
```

When switching an existing database between `NONE` and either of the other modes, you must run `vacuum()` for the change to take effect. Switching between `FULL` and `INCREMENTAL` does not require this.

## Database maintenance

### VACUUM

The `vacuum()` method rebuilds the database, reclaiming unused space.

```python
db.vacuum()
```

It cannot be called inside an active transaction.

### INCREMENTAL VACUUM

The `incremental_vacuum(pages=None)` method reclaims unused pages without rebuilding the entire database.

```python
db.incremental_vacuum(100)
```

In this example, SQLite attempts to reclaim up to 100 pages.

If `pages` is omitted, all available free pages are reclaimed:

```python
db.incremental_vacuum()
```

The `pages` parameter accepts a positive integer or `None`. An invalid value raises `ValueError`.

The method only works when the `INCREMENTAL` mode is enabled. In other modes, the call has no effect.

---

For more details, see [PRAGMA in the SQLite documentation](https://sqlite.org/pragma.html).

---
layout: default
title: Connections and transactions
lang: en
---

# Connections and transactions

[Home](index.md) · [Русский](../rus/transactions.md)

## Opening a connection

```python
from litecrate import Database

db = Database("players.sqlite3")
```

The `Database(db_path, timeout=30.0)` constructor accepts a string or a `pathlib.Path`. If the database file does not exist, SQLite creates it. `":memory:"` creates an in-memory database that lasts until the connection is closed.

The `timeout` parameter specifies how many seconds to wait for a database lock to be released; the default is `30.0`.

## Transactions

A `with db:` block groups multiple operations into a single transaction:

```python
with db:
    db.insert("players", login="ada")
    db.insert("players", login="guest")
```

Entering the block executes `BEGIN`. If the block completes successfully, `COMMIT` is called. If an exception leaves the block, `ROLLBACK` is performed; changes to the schema and the internal metadata cache are rolled back as well.

### Rollback example

```python
import sqlite3

try:
    with db:
        db.insert("players", login="ada")
        db.insert("players", login="ada")

except sqlite3.IntegrityError:
    print("Transaction rolled back")
```

This example assumes that the `players` table already exists and `login` has a `UNIQUE` constraint. The second insertion raises an exception, so the first insertion in the same block is rolled back too.

Outside `with db:`, the connection operates in autocommit mode. You can start another transaction after the previous one finishes.

**Limitations:** nested `with db:` blocks on the same instance are not supported and raise `RuntimeError`. The context manager handles transactions but **does not close** the connection. Errors while committing a transaction (`COMMIT`) are propagated to the caller.

## Closing a connection

```python
db.close()
```

If the connection must be closed even when an exception occurs, use `try/finally`:

```python
db = Database("players.sqlite3")
try:
    print(db.get_tables())
    
finally:
    db.close()
```

You can also use `contextlib.closing()` for this.

**Multithreading:** `Database` does not provide its own synchronization. If it is accessed from multiple threads, protect access with an external lock held for the entire transaction.

Journaling and space reclamation settings are documented separately: [Settings and maintenance](settings.md).

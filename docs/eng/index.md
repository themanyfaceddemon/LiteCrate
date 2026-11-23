---
layout: default
title: LiteCrate
lang: en
---

# LiteCrate

[Language selection](../index.md) · [Русский](../rus/index.md)

LiteCrate is a small Python library for working with SQLite. It lets you create tables, insert and update records using keyword arguments, and search using SQL conditions.

If records have different sets of fields, additional values can be stored as JSON without changing the table schema.

The library uses only the Python standard library and requires Python 3.13 or newer.

## Getting started

[Quick start](quickstart.md) - installation, creating your first table, and basic record operations.

## Documentation

- [Tables and data types](tables.md) - column definitions, flags, types, and table management.
- [Indexes](indexes.md) - automatic index creation and index management.
- [Working with records](records.md) - inserting, reading, updating, and deleting records.
- [Flexible fields and JSON](flexible.md) - additional fields, storage, and searching.
- [Connections and transactions](transactions.md) - connecting to a database, committing changes, and rolling back.
- [Settings and maintenance](settings.md) - journaling, `auto_vacuum`, `VACUUM`, and related operations.

## Links

[Source code on GitHub](https://github.com/themanyfaceddemon/LiteCrate) · [Package on PyPI](https://pypi.org/project/litecrate/)

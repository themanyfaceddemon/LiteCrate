---
layout: default
title: Documentation Test
---

# Documentation Test

A comprehensive Markdown rendering test for GitHub Pages.

This page is designed to evaluate **readability**, *typography*,
~~strikethrough~~, `inline code`, and [hyperlinks](https://github.com).

---

## 1. Typography

### Heading Level 3

#### Heading Level 4

##### Heading Level 5

###### Heading Level 6

This is a regular paragraph containing enough text to evaluate
line spacing, font rendering, contrast, and overall readability.
A good documentation theme should remain comfortable to read
even when paragraphs become relatively long.

**Bold text** should be clearly distinguishable.

*Italic text* should remain easy to read.

***Bold and italic text*** should be visually balanced.

Here is an example of `inline_code()` surrounded by normal text.

---

## 2. Lists

### Unordered List

- First item
- Second item
  - Nested item
  - Another nested item
- Third item

### Ordered List

1. Initialize the database.
2. Create the required tables.
3. Insert some records.
4. Query the database.
5. Close the connection.

### Task List

- [x] Create repository
- [x] Configure GitHub Pages
- [ ] Write API documentation
- [ ] Publish first release

---

## 3. Code Blocks

### Python

```python
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.connected = False

    def connect(self) -> None:
        """Establish a database connection."""
        if self.connected:
            raise RuntimeError("Database is already connected")

        self.connected = True

    def execute(self, query: str, *args: Any) -> None:
        print(f"Executing: {query}")
        print(f"Arguments: {args}")
```

### Bash

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -e .
python3 -m pytest
```

### JSON

```json
{
    "name": "example",
    "version": "1.0.0",
    "debug": false,
    "database": {
        "type": "sqlite",
        "timeout": 30.0
    }
}
```

### Plain Text

```text
[INFO]  Database initialized successfully
[DEBUG] Executing SQL query
[WARN]  Connection timeout approaching
[ERROR] Failed to execute transaction
```

---

## 4. Tables

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | Required | Database path |
| `timeout` | `float` | `30.0` | Connection timeout |
| `readonly` | `bool` | `False` | Read-only mode |
| `cache` | `bool` | `True` | Enable caching |

### Alignment Test

| Left | Center | Right |
|:-----|:------:|------:|
| Alpha | Beta | 123 |
| Gamma | Delta | 456 |
| Epsilon | Zeta | 789 |

---

## 5. Blockquotes

> This is a standard blockquote.
> It should be visually separated from the surrounding text.

> **Warning**
>
> This operation may permanently modify stored data.
> Always create a backup before proceeding.

---

## 6. Links

- [GitHub](https://github.com)
- [Python Documentation](https://docs.python.org/3/)
- [SQLite Documentation](https://sqlite.org/docs.html)
- [Back to top](#documentation-test)

---

## 7. Images

![Test image](https://placehold.co/800x240/20232a/e6edf3/png?text=Image+Rendering+Test)

---

## 8. HTML Elements

<details>
<summary>Click to expand</summary>

This is a collapsible section containing additional information.

```python
print("Hello from the hidden section!")
```

</details>

---

## 9. Special Characters

**Mathematical symbols:** α β γ δ λ π Ω ∞ ≠ ≤ ≥

**Arrows:** → ← ↑ ↓ ⇒ ⇔

**Symbols:** © ® ™ § ¶

**Unicode:** Ελληνικά, 日本語, Русский, 中文

---

## 10. Long Paragraph

Documentation should prioritize clarity and accessibility.
A well-designed theme must provide sufficient contrast between
foreground and background colors, especially when displaying
large sections of technical information. Code examples should
be distinguishable from regular text without becoming visually
overwhelming. Tables should remain readable, headings should
establish a clear hierarchy, and hyperlinks should be immediately
recognizable without distracting from surrounding content.

---

## 11. API Reference Example

### `Database.execute()`

Execute an SQL statement with optional positional parameters.

**Signature:**

```python
def execute(self, query: str, *args: object) -> None:
    ...
```

**Parameters:**

- `query` — SQL statement to execute.
- `args` — Positional query parameters.

**Raises:**

- `RuntimeError` — If the database connection is unavailable.
- `ValueError` — If the query is invalid.

**Example:**

```python
db.execute(
    "INSERT INTO users (name, age) VALUES (?, ?)",
    "Alice",
    24,
)
```

---

*End of Markdown rendering test.*

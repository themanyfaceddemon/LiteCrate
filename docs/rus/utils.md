---
layout: default
title: Утилиты
lang: ru
---

# Утилиты

[Главная](index.md) · [English](../eng/utils.md)

**Внимание! Внутренний API**

Модуль `litecrate.utils` предназначен преимущественно для внутреннего использования библиотекой и **не входит в публичный API LiteCrate**.

Функции модуля доступны для прямого импорта, однако обратная совместимость для них не гарантируется. Их сигнатуры, поведение и названия могут изменяться или удаляться без предварительного уведомления, в том числе при обновлениях, не меняющих основной номер версии.

Использование этих функций в стороннем коде осуществляется на собственный риск.

## Имена таблиц и колонок

| Функция | Назначение |
|---|---|
| `normalize_identifier(identifier)` | Проверяет допустимость имени, приводит его к нижнему регистру. |
| `normalize_identifiers(*identifiers)` | То же для нескольких имён; возвращает кортеж. |
| `sanitize_identifier(identifier)` | Экранирует имя двойными SQL-кавычками. |
| `sanitize_identifiers(*identifiers)` | То же для нескольких имён; возвращает кортеж. |
| `check_table_name(*names)` | Проверяет, что имя не зарезервировано для таблицы метаданных. |
| `check_column_name(*names)` | Проверяет, что имя не зарезервировано для гибких данных. |

Нормализация принимает только ASCII-имена без нулевого символа. Имя `_litecrate_meta` зарезервировано для служебной таблицы, а `_data` - для служебной колонки.

```python
from litecrate.utils import normalize_identifier, sanitize_identifier

name = normalize_identifier('Display"Name')
print(sanitize_identifier(name))
# "display""name"
```

Экранирование идентификаторов не заменяет параметризацию **значений**: для значений SQL-запросов используй `?`.

## Генерация схемы

| Функция или тип | Назначение |
|---|---|
| `ColumBitEnum` | `IntFlag` со значениями `INDEX`, `NOT_NULL`, `PRIMARY`, `UNIQUE`. |
| `ColumBitEnum.all_flags()` | Возвращает общую маску флагов. |
| `get_index_identifier(table, colum)` | Формирует имя индекса для пары таблица/колонка. |
| `parse_colum_into_sql(table_name, flags, colum_name, colum_type=None)` | Возвращает `(column_sql, index_sql)`; второй элемент - `None`, если отдельный индекс не нужен. |

```python
from litecrate.utils import ColumBitEnum, parse_colum_into_sql

flags = ColumBitEnum.INDEX | ColumBitEnum.NOT_NULL
column_sql, index_sql = parse_colum_into_sql(
    "players", flags, "level", int
)
```

Написание `ColumBitEnum`, `colum` и `parse_colum_into_sql` сохранено таким, как оно используется в API.

Для колонок `dict` и `list` используй `Database.create_table()`: он сохраняет информацию о типе для последующего восстановления JSON. Подробнее: [Таблицы и типы данных](tables.md).

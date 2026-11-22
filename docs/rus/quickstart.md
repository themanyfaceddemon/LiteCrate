---
layout: default
title: Быстрый старт
lang: ru
---

# Быстрый старт

[Главная](index.md)

## Установка

Для LiteCrate нужен Python 3.13 или новее. Сторонние зависимости для работы библиотеки не требуются.

```bash
python -m pip install litecrate
```

## Первая таблица

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

Здесь `create_table()` создаёт таблицу с тремя колонками. Флаг `p` задаёт первичный ключ, а `un` - обязательное уникальное значение. `insert()` добавляет строку, `update()` меняет её по условию, а `select_one()` возвращает словарь с найденными полями.

`with db:` объединяет операции в транзакцию: при успешном завершении изменения фиксируются, при исключении - откатываются. Этот блок **не закрывает** соединение; для закрытия вызывается `db.close()`.

## Сохранение данных в файле

В примере используется `":memory:"` - база в оперативной памяти, которая исчезнет после закрытия соединения. Для сохранения данных между запусками передай путь к файлу:

```python
db = Database("players.sqlite3")
```

Если файла нет, SQLite создаст его автоматически.

## Что дальше

[Таблицы и типы данных](tables.md) · [Работа с записями](records.md) · [Гибкие поля и JSON](flexible.md) · [Соединения и транзакции](transactions.md)

import sqlite3
import statistics
import time

from litecrate import Database

ROUNDS = 50


def benchmark_litecrate(count: int, separate_transactions: bool) -> float:
    db = Database(":memory:")

    with db:
        db.create_table(
            "users",
            ("unp", "login", str),
            ("n", "password", str),
        )

    start = time.perf_counter()

    if separate_transactions:
        for i in range(count):
            db.insert("users", login=f"user_{i}", password="hash")

    else:
        with db:
            for i in range(count):
                db.insert("users", login=f"user_{i}", password="hash")

    elapsed = time.perf_counter() - start
    db.close()
    return elapsed


def benchmark_sqlite(count: int, separate_transactions: bool) -> float:
    conn = sqlite3.connect(":memory:", isolation_level=None)

    conn.execute(
        "CREATE TABLE users (login TEXT PRIMARY KEY NOT NULL, password TEXT NOT NULL)"
    )

    query = "INSERT INTO users (login, password) VALUES (?, ?)"
    start = time.perf_counter()

    if separate_transactions:
        for i in range(count):
            conn.execute(query, (f"user_{i}", "hash"))

    else:
        conn.execute("BEGIN")
        for i in range(count):
            conn.execute(query, (f"user_{i}", "hash"))

        conn.execute("COMMIT")

    elapsed = time.perf_counter() - start
    conn.close()
    return elapsed


def run(count: int, separate_transactions: bool) -> None:
    lite_times = []
    sqlite_times = []

    for i in range(ROUNDS):
        if i % 2 == 0:
            lite = benchmark_litecrate(count, separate_transactions)
            raw = benchmark_sqlite(count, separate_transactions)

        else:
            raw = benchmark_sqlite(count, separate_transactions)
            lite = benchmark_litecrate(count, separate_transactions)

        lite_times.append(lite)
        sqlite_times.append(raw)

    lite = statistics.median(lite_times)
    raw = statistics.median(sqlite_times)

    print(f"\nInserts: {count:,}")
    print(f"Separate transactions: {separate_transactions}")
    print(f"SQLite:    {raw:.4f} s | {raw / count * 1e6:.2f} us/op")
    print(f"LiteCrate: {lite:.4f} s | {lite / count * 1e6:.2f} us/op")
    print(f"Overhead:  {lite / raw:.2f}x")


if __name__ == "__main__":
    run(10_000, separate_transactions=False)
    run(10_000, separate_transactions=True)

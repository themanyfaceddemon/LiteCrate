from src.litecrate.database import Database

db = Database(":memory:")

db.create_table(
    "foo",
    "p:name:text",
    "i:name2:text",
    flexible=True,
)

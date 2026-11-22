from importlib.metadata import PackageNotFoundError, version

from .database.db_class import Database

try:
    __version__ = version("litecrate")

except PackageNotFoundError:
    __version__ = "dev"

__all__ = [
    "Database",
    "__version__",
]

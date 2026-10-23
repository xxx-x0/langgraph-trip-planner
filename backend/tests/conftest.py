"""Keep ordinary pytest runs out of the local user's travel database."""
import os
from tempfile import TemporaryDirectory
from pathlib import Path

_test_database = TemporaryDirectory(prefix="ltp-pytest-")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(_test_database.name) / 'trips.db'}",
)

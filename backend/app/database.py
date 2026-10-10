"""Readiness probe: inspect an existing SQLite file without creating or mutating it."""
from contextlib import closing
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 1


def database_ready(path: Path) -> bool:
    # Open read-only so readiness never bootstraps an empty database.
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                return False
            # Phase 9 owns the complete schema and importer; confirm its table is queryable.
            connection.execute("SELECT id FROM providers LIMIT 1").fetchall()
            return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    except (sqlite3.Error, OSError, ValueError):
        return False

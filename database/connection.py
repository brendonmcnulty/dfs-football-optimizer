from __future__ import annotations

import sqlite3
from pathlib import Path


def create_connection(database_path: Path) -> sqlite3.Connection:
    """Open and configure a SQLite database connection."""

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection
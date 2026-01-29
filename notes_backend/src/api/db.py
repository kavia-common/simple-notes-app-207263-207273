"""Database helpers for the notes backend.

This backend uses the SQLite database file produced by the `notes_database` container.
Connection is configured via environment variable `SQLITE_DB`.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional


# PUBLIC_INTERFACE
def get_sqlite_db_path() -> str:
    """Return the absolute path to the SQLite DB file used by the backend.

    Expects env var SQLITE_DB to be set by the runtime environment.

    Returns:
        Absolute filesystem path to the SQLite DB file.

    Raises:
        RuntimeError: If SQLITE_DB is missing or points to a non-existent file.
    """
    db_path = os.getenv("SQLITE_DB")
    if not db_path:
        raise RuntimeError(
            "Missing required environment variable SQLITE_DB. "
            "It must point to the SQLite database file produced by notes_database."
        )

    # Allow relative paths but normalize to absolute.
    db_path = os.path.abspath(db_path)

    # Note: The db file may not exist in very early boot scenarios, but for this app
    # we expect the database container to have created it.
    if not os.path.exists(db_path):
        raise RuntimeError(
            f"SQLITE_DB points to '{db_path}', but that file does not exist."
        )

    return db_path


def _dict_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict:
    """sqlite3 row factory producing dicts keyed by column names."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


# PUBLIC_INTERFACE
def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection configured for this API.

    Returns:
        sqlite3.Connection: connection with foreign keys enabled and dict row factory.
    """
    conn = sqlite3.connect(get_sqlite_db_path(), check_same_thread=False)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# PUBLIC_INTERFACE
def ensure_schema() -> None:
    """Ensure the required `notes` schema exists.

    This is a safety net in case the DB is empty. It mirrors the schema created by
    the notes_database container.
    """
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS notes_set_updated_at
            AFTER UPDATE ON notes
            FOR EACH ROW
            BEGIN
                UPDATE notes
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
            """
        )
        conn.commit()
    finally:
        if conn is not None:
            conn.close()

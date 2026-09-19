from __future__ import annotations

import sqlite3
from pathlib import Path

from nottle_ai.database import Database

from .conftest import make_settings


def test_legacy_call_table_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stream_sid TEXT, call_sid TEXT, caller TEXT, created_at TEXT,
                status TEXT, transcript TEXT, summary TEXT,
                is_lead INTEGER DEFAULT 1, booking_requested INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO calls(caller,status) VALUES('+61400000000','completed')"
        )

    database = Database(path, make_settings(path))
    database.init()
    with database.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(calls)")}
        row = conn.execute("SELECT * FROM calls LIMIT 1").fetchone()

    assert {"business_id", "called_number", "completed_at", "duration_seconds"} <= columns
    assert row["business_id"] is not None

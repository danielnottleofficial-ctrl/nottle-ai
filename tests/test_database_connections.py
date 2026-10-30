import sqlite3
from dataclasses import replace

import pytest

from nottle_ai.bookings import Bookings
from nottle_ai.database import Database


def assert_closed(conn):
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT 1")


def test_transaction_commits_and_releases_connection(settings):
    db = Database(settings.database_path, settings)
    with db.connect() as conn:
        conn.execute("CREATE TABLE example (value TEXT)")
        conn.execute("INSERT INTO example VALUES ('saved')")
    assert_closed(conn)
    with db.connect() as check:
        assert check.execute("SELECT value FROM example").fetchone()[0] == "saved"


def test_failed_transaction_rolls_back_and_releases_connection(settings):
    db = Database(settings.database_path, settings)
    with db.connect() as conn:
        conn.execute("CREATE TABLE example (value TEXT)")
    with pytest.raises(ValueError, match="cancel"):
        with db.connect() as failed:
            failed.execute("INSERT INTO example VALUES ('discarded')")
            raise ValueError("cancel")
    assert_closed(failed)
    with db.connect() as check:
        assert check.execute("SELECT COUNT(*) FROM example").fetchone()[0] == 0


def test_idle_booking_worker_releases_connections_without_gc(settings, monkeypatch):
    settings = replace(settings, app_approval_enabled=True)
    db = Database(settings.database_path, settings)
    db.init()
    service = Bookings(db, settings)
    original = db.connect
    connections = []

    def track():
        conn = original()
        connections.append(conn)  # Keep references: cleanup must not depend on GC.
        return conn

    monkeypatch.setattr(db, "connect", track)
    for _ in range(100):
        assert service.tick() is False
    assert len(connections) == 100
    for conn in connections:
        assert_closed(conn)

"""Pluggable persistence backend."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class NullBackend:
    """No-op backend (in-memory mode, default)."""

    def put(self, service: str, rtype: str, id: str, data: dict) -> None:
        pass

    def delete(self, service: str, rtype: str, id: str) -> None:
        pass

    def get_all(self, service: str, rtype: str) -> list[dict]:
        return []


class SqliteBackend:
    """Persist resources as JSON blobs in SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resources (
                service TEXT NOT NULL,
                rtype   TEXT NOT NULL,
                id      TEXT NOT NULL,
                data    TEXT NOT NULL,
                PRIMARY KEY (service, rtype, id)
            )
            """
        )
        self._conn.commit()

    def put(self, service: str, rtype: str, id: str, data: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO resources (service, rtype, id, data) VALUES (?, ?, ?, ?)",
            (service, rtype, id, json.dumps(data)),
        )
        self._conn.commit()

    def delete(self, service: str, rtype: str, id: str) -> None:
        self._conn.execute(
            "DELETE FROM resources WHERE service=? AND rtype=? AND id=?",
            (service, rtype, id),
        )
        self._conn.commit()

    def get_all(self, service: str, rtype: str) -> list[dict]:
        cursor = self._conn.execute(
            "SELECT data FROM resources WHERE service=? AND rtype=?",
            (service, rtype),
        )
        return [json.loads(row[0]) for row in cursor.fetchall()]


def create_backend(mode: str, db_path: str) -> NullBackend | SqliteBackend:
    if mode == "sqlite":
        import os
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        return SqliteBackend(db_path)
    return NullBackend()

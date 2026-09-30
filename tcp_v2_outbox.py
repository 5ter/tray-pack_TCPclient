"""Durable local queue for inspection results awaiting server confirmation."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from threading import RLock


class LocalResultOutbox:
    """Store each result locally until the API confirms its event ID."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_results (
                event_id TEXT PRIMARY KEY,
                part_number TEXT NOT NULL,
                run_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('OK', 'NG')),
                timestamp_utc TEXT NOT NULL,
                machine_id TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def add(self, result: dict[str, str]) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO pending_results (
                    event_id, part_number, run_id, status, timestamp_utc, machine_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result["eventId"], result["partNumber"], result["runId"],
                    result["status"], result["timestampUtc"], result["machineId"],
                ),
            )
            self._connection.commit()

    def pending(self, limit: int = 100) -> list[dict[str, str]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT event_id, part_number, run_id, status, timestamp_utc, machine_id
                FROM pending_results
                ORDER BY rowid
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "eventId": row[0], "partNumber": row[1], "runId": row[2],
                "status": row[3], "timestampUtc": row[4], "machineId": row[5],
            }
            for row in rows
        ]

    def remove_delivered(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._lock:
            self._connection.executemany(
                "DELETE FROM pending_results WHERE event_id = ?",
                [(event_id,) for event_id in event_ids],
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

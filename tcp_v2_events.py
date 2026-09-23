"""Inspection event model and durable local event queue."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


@dataclass(frozen=True)
class InspectionEvent:
    """One new M7 or M8 result seen by the PC."""

    event_id: str
    machine_id: str
    status: str
    occurred_at_utc: str
    source_coil: int

    @classmethod
    def create(cls, machine_id: str, status: str, source_coil: int) -> "InspectionEvent":
        return cls(
            event_id=str(uuid.uuid4()),
            machine_id=machine_id,
            status=status,
            occurred_at_utc=datetime.now(timezone.utc).isoformat(),
            source_coil=source_coil,
        )

    def as_json_line(self) -> str:
        """Compatible with the existing line-based TCP result receiver."""
        return json.dumps(asdict(self), separators=(",", ":")) + "\n"


class EventOutbox:
    """SQLite queue: store an event locally before sending it elsewhere."""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inspection_events (
                event_id TEXT PRIMARY KEY,
                machine_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('OK', 'NG')),
                occurred_at_utc TEXT NOT NULL,
                source_coil INTEGER NOT NULL,
                delivered_at_utc TEXT
            )
            """
        )
        self._connection.commit()

    def add(self, event: InspectionEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO inspection_events (
                event_id, machine_id, status, occurred_at_utc, source_coil
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (event.event_id, event.machine_id, event.status, event.occurred_at_utc, event.source_coil),
        )
        self._connection.commit()

    def pending(self, limit: int = 100) -> list[InspectionEvent]:
        rows = self._connection.execute(
            """
            SELECT event_id, machine_id, status, occurred_at_utc, source_coil
            FROM inspection_events
            WHERE delivered_at_utc IS NULL
            ORDER BY occurred_at_utc, event_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [InspectionEvent(*row) for row in rows]

    def mark_delivered(self, event_id: str) -> None:
        self._connection.execute(
            "UPDATE inspection_events SET delivered_at_utc = ? WHERE event_id = ?",
            (datetime.now(timezone.utc).isoformat(), event_id),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

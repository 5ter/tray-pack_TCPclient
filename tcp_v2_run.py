"""Current production run selection and PLC-result context."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from threading import RLock
from typing import Any
import uuid

from tcp_v2_config import Settings
from tcp_v2_db import DatabaseApiClient
from tcp_v2_events import InspectionEvent
from tcp_v2_sender import ResultSubmitter


class RunError(RuntimeError):
    """The requested production run could not be started or loaded."""


@dataclass(frozen=True)
class ActiveRun:
    part_number: str
    run_id: str
    started_at_utc: str


class RunStateStore:
    """Keep the current part/run context across a PC service restart."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    def load(self) -> ActiveRun | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return ActiveRun(
                part_number=str(data["part_number"]),
                run_id=str(data["run_id"]),
                started_at_utc=str(data["started_at_utc"]),
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise RunError(f"Cannot load current production run from {self._path}: {error}") from error

    def save(self, run: ActiveRun) -> None:
        temporary_path = self._path.with_suffix(".tmp")
        try:
            temporary_path.write_text(json.dumps(asdict(run), indent=2), encoding="utf-8")
            temporary_path.replace(self._path)
        except OSError as error:
            raise RunError(f"Cannot save current production run: {error}") from error


class ProductionRunController:
    """Select the part number that tags subsequent PLC OK/NG results."""

    def __init__(
        self,
        settings: Settings,
        database: DatabaseApiClient,
        submitter: ResultSubmitter,
    ) -> None:
        self._settings = settings
        self._database = database
        self._submitter = submitter
        self._store = RunStateStore(settings.active_run_path)
        self._lock = RLock()
        self._active_run = self._store.load()

    def start_run(self, part_number: str) -> dict[str, Any]:
        cleaned_part_number = part_number.strip()
        if not cleaned_part_number:
            raise RunError("partNumber is required")
        parts = self._database.list_parts()
        if not any(part["partNumber"] == cleaned_part_number for part in parts):
            raise RunError(f"Part number '{cleaned_part_number}' is not registered")

        run = ActiveRun(
            part_number=cleaned_part_number,
            run_id=str(uuid.uuid4()),
            started_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._store.save(run)
            self._active_run = run
        logging.info("Started production run=%s for part=%s", run.run_id, run.part_number)
        return {"active": True, **asdict(run)}

    def summary(self) -> dict[str, Any]:
        with self._lock:
            run = self._active_run
        if run is None:
            return {"active": False}

        counts = self._database.get_run_summary(run.run_id, run.part_number)
        return {"active": True, **asdict(run), **counts}

    def handle_inspection_event(self, event: InspectionEvent) -> None:
        with self._lock:
            run = self._active_run
        if run is None:
            logging.warning("Ignoring %s event because no production run is selected", event.status)
            return

        payload = {
            "eventId": event.event_id,
            "partNumber": run.part_number,
            "runId": run.run_id,
            "status": event.status,
            "timestampUtc": event.occurred_at_utc,
            "machineId": event.machine_id,
        }
        if not self._submitter.enqueue(payload):
            logging.critical(
                "Inspection result %s for run=%s could not be saved locally; check PC disk and outbox permissions",
                event.event_id, run.run_id,
            )

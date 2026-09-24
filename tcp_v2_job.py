"""Active job, PC-side Box-ID generation, and label/DB compatibility flow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import logging
from pathlib import Path
from threading import RLock
from typing import Any

from tcp_v2_config import Settings
from tcp_v2_db import DatabaseApiClient, DatabaseApiError
from tcp_v2_events import InspectionEvent
from tcp_v2_printer import LabelData, PrinterError, SatoPrinter


class JobError(RuntimeError):
    """The job cannot safely start, reset, or process a tray event."""


@dataclass
class ActiveJob:
    """The same product/label fields formerly held in Node `currentProjectData`."""

    customer_part_number: str
    date_code: str
    quantity: int
    tray_amount: int
    delivery_date: str
    box_id: str
    vendor_code: str
    box_counter: int
    spec: str
    remarks: str

    @classmethod
    def from_database(
        cls,
        database_data: dict[str, Any],
        delivery_date: str,
        spec: str,
    ) -> "ActiveJob":
        initial_box_id = str(database_data.get("Box_ID") or "")
        if len(initial_box_id) < 21:
            raise JobError("Database Box_ID must contain at least 21 characters")
        try:
            box_counter = int(initial_box_id[14:19])
        except ValueError as error:
            raise JobError("Database Box_ID positions 15-19 must be numeric") from error

        try:
            quantity = int(database_data.get("Quantity"))
            tray_amount = int(database_data.get("Tray_Amount"))
        except (TypeError, ValueError) as error:
            raise JobError("Database Quantity and Tray_Amount must be integers") from error
        if quantity <= 0 or tray_amount <= 0:
            raise JobError("Database Quantity and Tray_Amount must be greater than zero")

        try:
            parsed_delivery_date = date.fromisoformat(delivery_date)
        except ValueError as error:
            raise JobError("deliveryDate must use YYYY-MM-DD format") from error

        now = datetime.now()
        iso_year, iso_week, _ = now.isocalendar()
        return cls(
            customer_part_number=str(database_data.get("Cust_PN") or ""),
            date_code=f"{iso_year}{iso_week:02d}",
            quantity=quantity,
            tray_amount=tray_amount,
            delivery_date=parsed_delivery_date.strftime("%d/%m/%Y"),
            box_id=initial_box_id,
            vendor_code=initial_box_id[:8],
            box_counter=box_counter,
            spec=spec,
            remarks=str(database_data.get("Remarks") or ""),
        )

    def next_box_id(self, today: date | None = None) -> tuple[str, int]:
        """Use the original `Vendor + YYMMDD + five-digit counter + MY` format."""
        new_counter = self.box_counter + 1
        if new_counter > 99999:
            raise JobError("Box-ID counter exceeded five digits")
        actual_date = today or date.today()
        yymmdd = actual_date.strftime("%y%m%d")
        return f"{self.vendor_code}{yymmdd}{new_counter:05d}MY", new_counter


class JobStateStore:
    """Persist the active PC job; it survives an application restart."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    def load(self) -> tuple[ActiveJob | None, str | None, int | None]:
        if not self._path.exists():
            return None, None, None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            active_job = data.get("active_job")
            pending = data.get("pending_box_id")
            pending_counter = data.get("pending_counter")
            if pending is not None and not isinstance(pending, str):
                raise TypeError("pending_box_id must be a string or null")
            if pending_counter is not None and not isinstance(pending_counter, int):
                raise TypeError("pending_counter must be an integer or null")
            return ActiveJob(**active_job) if active_job else None, pending, pending_counter
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise JobError(f"Cannot load local active job state: {error}") from error

    def save(
        self,
        job: ActiveJob | None,
        pending_box_id: str | None = None,
        pending_counter: int | None = None,
    ) -> None:
        temporary_path = self._path.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps(
                    {
                        "active_job": asdict(job) if job else None,
                        "pending_box_id": pending_box_id,
                        "pending_counter": pending_counter,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary_path.replace(self._path)
        except OSError as error:
            raise JobError(f"Cannot save local active job state: {error}") from error


class JobController:
    """Owns the active job and handles final M7/M8 events from the PLC poller."""

    def __init__(self, settings: Settings, database: DatabaseApiClient, printer: SatoPrinter) -> None:
        self._settings = settings
        self._database = database
        self._printer = printer
        self._store = JobStateStore(settings.job_state_path)
        self._lock = RLock()
        self._job, self._pending_box_id, self._pending_counter = self._store.load()

    def summary(self) -> dict[str, Any]:
        with self._lock:
            if self._job is None:
                return {"active": False, "printingEnabled": self._settings.enable_printing}
            return {
                "active": True,
                "printingEnabled": self._settings.enable_printing,
                "spec": self._job.spec,
                "customerPartNumber": self._job.customer_part_number,
                "quantity": self._job.quantity,
                "trayAmount": self._job.tray_amount,
                "deliveryDate": self._job.delivery_date,
                "lastBoxId": self._job.box_id,
                "lastBoxCounter": self._job.box_counter,
                "pendingBoxId": self._pending_box_id,
            }

    def start(self, delivery_date: str, spec: str) -> dict[str, Any]:
        cleaned_spec = spec.strip()
        if not cleaned_spec:
            raise JobError("spec is required")

        database_data = self._database.get_project_data(cleaned_spec)
        job = ActiveJob.from_database(database_data, delivery_date, cleaned_spec)
        with self._lock:
            if self._pending_box_id is not None:
                raise JobError(
                    "Cannot replace the job while a previous Box ID is pending. "
                    "Resolve the printer/database error first."
                )
            self._job = job
            self._store.save(job, None, None)
        logging.info("Started job for spec=%s, Box_ID=%s", job.spec, job.box_id)
        return self.summary()

    def reset(self) -> None:
        with self._lock:
            if self._pending_box_id is not None:
                raise JobError(
                    "Cannot reset while a Box ID is pending. Resolve the printer/database error first."
                )
            self._job = None
            self._store.save(None, None, None)
        logging.info("Active PC job reset")

    def handle_inspection_event(self, event: InspectionEvent) -> None:
        """Perform PC-side label processing for a final PLC result.

        M8/NG creates no shipping label. M7/OK prints one label only when
        `ENABLE_PRINTING=true`; otherwise it is a dry run and changes nothing
        in the existing database.
        """
        with self._lock:
            if self._job is None:
                logging.warning("Ignoring %s event: no active job", event.status)
                return
            if event.status == "NG":
                logging.info("Recorded NG inspection event: label not printed")
                return

            if self._pending_box_id is not None:
                logging.error(
                    "Ignoring new OK event because Box_ID=%s is pending printer/database resolution",
                    self._pending_box_id,
                )
                return

            next_box_id, next_counter = self._job.next_box_id()
            if not self._settings.enable_printing:
                logging.info(
                    "DRY RUN: M7/OK would print Box_ID=%s for spec=%s",
                    next_box_id,
                    self._job.spec,
                )
                return

            label = LabelData(
                customer_part_number=self._job.customer_part_number,
                date_code=self._job.date_code,
                quantity=self._job.quantity,
                delivery_date=self._job.delivery_date,
                box_id=next_box_id,
                spec=self._job.spec,
                remarks=self._job.remarks,
            )

            # Existing API has no atomic Box-ID reservation. Persist a pending
            # ID before printing. If print/DB fails, further automatic labels
            # are blocked rather than silently reusing a possibly printed ID.
            self._pending_box_id = next_box_id
            self._pending_counter = next_counter
            self._store.save(self._job, self._pending_box_id, self._pending_counter)
            try:
                self._printer.print_label(label)
                self._database.update_box_id(self._job.spec, next_box_id)
            except (PrinterError, DatabaseApiError, JobError) as error:
                logging.error(
                    "Box_ID=%s remains pending; resolve before the next label: %s",
                    next_box_id,
                    error,
                )
                return

            self._job.box_id = next_box_id
            self._job.box_counter = next_counter
            self._pending_box_id = None
            self._pending_counter = None
            self._store.save(self._job, None, None)
            logging.info("Printed and saved Box_ID=%s", next_box_id)

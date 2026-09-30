"""Durably queue inspection results and retry batched API delivery."""

from __future__ import annotations

import logging
from threading import Event, Thread
from time import monotonic

from tcp_v2_db import DatabaseApiClient, DatabaseApiError
from tcp_v2_outbox import LocalResultOutbox


class ResultSubmitter:
    """Write results to SQLite immediately, then flush them every 10 seconds."""

    def __init__(
        self,
        database: DatabaseApiClient,
        outbox: LocalResultOutbox,
        flush_interval_seconds: float = 10.0,
        batch_size: int = 100,
    ) -> None:
        if flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds must be greater than zero")
        if batch_size <= 0 or batch_size > 100:
            raise ValueError("batch_size must be between 1 and 100 (the API limit)")
        self._database = database
        self._outbox = outbox
        self._flush_interval_seconds = flush_interval_seconds
        self._batch_size = batch_size
        self._stop_event = Event()
        self._thread = Thread(target=self._work, name="result-submit", daemon=True)
        self._thread.start()

    def enqueue(self, payload: dict[str, str]) -> bool:
        """Persist one result before returning to the PLC polling loop."""
        try:
            self._outbox.add(payload)
        except Exception:
            logging.critical(
                "CRITICAL: could not persist %s result for run=%s in the local outbox",
                payload.get("status"), payload.get("runId"),
                exc_info=True,
            )
            return False

        logging.info(
            "Queued %s result locally for part=%s run=%s event=%s",
            payload["status"], payload["partNumber"], payload["runId"], payload["eventId"],
        )
        return True

    def _flush_once(self) -> None:
        try:
            batch = self._outbox.pending(self._batch_size)
        except Exception:
            logging.exception("Could not read pending inspection results from the local outbox")
            return
        if not batch:
            return

        batch_ids = {event["eventId"] for event in batch}
        try:
            accepted_ids = self._database.record_inspection_batch(batch)
        except DatabaseApiError as error:
            logging.warning(
                "Server did not confirm %s queued result(s); they remain in the local outbox for retry: %s",
                len(batch), error,
            )
            return
        except Exception:
            logging.exception(
                "Unexpected error sending %s queued result(s); they remain in the local outbox",
                len(batch),
            )
            return

        confirmed_ids = list(dict.fromkeys(event_id for event_id in accepted_ids if event_id in batch_ids))
        if not confirmed_ids:
            logging.error(
                "Server accepted no recognizable event IDs from a batch of %s; results remain queued",
                len(batch),
            )
            return

        try:
            self._outbox.remove_delivered(confirmed_ids)
        except Exception:
            # Retrying is safe because the server enforces a unique event ID.
            logging.exception(
                "Server confirmed %s result(s), but local acknowledgement failed; they will be retried safely",
                len(confirmed_ids),
            )
            return

        logging.info("Server confirmed and local outbox cleared %s/%s result(s)", len(confirmed_ids), len(batch))
        if len(confirmed_ids) < len(batch):
            logging.warning("%s result(s) remain queued because the server did not confirm them", len(batch) - len(confirmed_ids))

    def _work(self) -> None:
        next_flush = monotonic() + self._flush_interval_seconds
        while not self._stop_event.is_set():
            delay = max(0.0, next_flush - monotonic())
            if self._stop_event.wait(delay):
                break
            self._flush_once()
            next_flush += self._flush_interval_seconds
            while next_flush <= monotonic():
                next_flush += self._flush_interval_seconds
        # Try one final send on orderly shutdown. Failures remain on disk and
        # are retried the next time this service starts.
        self._flush_once()

    def close(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=10.0)
        if self._thread.is_alive():
            logging.error("Result sender did not stop within 10 seconds; pending results remain in SQLite")

"""Offline tests for durable result queuing and retry acknowledgement."""

from pathlib import Path
import tempfile
import unittest

from tcp_v2_db import DatabaseApiError
from tcp_v2_outbox import LocalResultOutbox
from tcp_v2_sender import ResultSubmitter


def inspection_result(event_id: str) -> dict[str, str]:
    return {
        "eventId": event_id,
        "partNumber": "PART-123",
        "runId": "7c90ad28-8fba-4dc4-97f7-51c98029efad",
        "status": "OK",
        "timestampUtc": "2026-09-30T01:02:03.000000+00:00",
        "machineId": "TRAY-PACK-01",
    }


class FakeDatabaseApi:
    def __init__(self) -> None:
        self.fail = False
        self.accepted_ids: list[str] | None = None
        self.batches: list[list[dict[str, str]]] = []

    def record_inspection_batch(self, events: list[dict[str, str]]) -> list[str]:
        self.batches.append(events)
        if self.fail:
            raise DatabaseApiError("simulated API outage")
        if self.accepted_ids is not None:
            return self.accepted_ids
        return [event["eventId"] for event in events]


class LocalResultOutboxTests(unittest.TestCase):
    def test_result_survives_reopening_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result_outbox.sqlite3"
            expected = inspection_result("6f1d2dc6-581e-41a6-91b4-9edaf931ef6b")

            first = LocalResultOutbox(path)
            try:
                first.add(expected)
            finally:
                first.close()

            reopened = LocalResultOutbox(path)
            try:
                self.assertEqual(reopened.pending(), [expected])
            finally:
                reopened.close()

    def test_failed_send_is_retained_then_removed_after_ack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = LocalResultOutbox(Path(directory) / "result_outbox.sqlite3")
            database = FakeDatabaseApi()
            sender = ResultSubmitter(database, outbox, flush_interval_seconds=3600)
            result = inspection_result("6f1d2dc6-581e-41a6-91b4-9edaf931ef6b")
            try:
                self.assertTrue(sender.enqueue(result))
                database.fail = True
                sender._flush_once()
                self.assertEqual(outbox.pending(), [result])

                database.fail = False
                sender._flush_once()
                self.assertEqual(outbox.pending(), [])
                self.assertEqual(len(database.batches), 2)
            finally:
                sender.close()
                outbox.close()

    def test_only_confirmed_event_ids_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outbox = LocalResultOutbox(Path(directory) / "result_outbox.sqlite3")
            database = FakeDatabaseApi()
            sender = ResultSubmitter(database, outbox, flush_interval_seconds=3600)
            first = inspection_result("6f1d2dc6-581e-41a6-91b4-9edaf931ef6b")
            second = inspection_result("955d9702-a29c-4d71-a3f9-e5c68bf10a58")
            try:
                self.assertTrue(sender.enqueue(first))
                self.assertTrue(sender.enqueue(second))
                database.accepted_ids = [first["eventId"]]
                sender._flush_once()
                self.assertEqual(outbox.pending(), [second])

                # Allow the shutdown flush to clean up through the fake API.
                database.accepted_ids = None
            finally:
                sender.close()
                outbox.close()


if __name__ == "__main__":
    unittest.main()

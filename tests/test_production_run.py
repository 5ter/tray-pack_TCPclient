"""Offline tests for binding PLC results to the selected operator and run."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tcp_v2_config import Settings
from tcp_v2_events import InspectionEvent
from tcp_v2_run import ProductionRunController


class FakeDatabase:
    def list_parts(self) -> list[dict[str, str]]:
        return [{"partNumber": "PART-123"}]

    def get_run_summary(self, run_id: str, part_number: str) -> dict[str, int]:
        return {"okCount": 0, "ngCount": 0, "totalCount": 0}


class FakeSubmitter:
    def __init__(self) -> None:
        self.payloads: list[dict[str, str]] = []

    def enqueue(self, payload: dict[str, str]) -> bool:
        self.payloads.append(payload)
        return True


class ProductionRunControllerTests(unittest.TestCase):
    def test_operator_is_saved_and_attached_to_plc_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(Settings(), active_run_path=Path(directory) / "active_run.json")
            database = FakeDatabase()
            submitter = FakeSubmitter()
            controller = ProductionRunController(settings, database, submitter)

            run = controller.start_run("PART-123", "Operator A")
            controller.handle_inspection_event(
                InspectionEvent(
                    event_id="6f1d2dc6-581e-41a6-91b4-9edaf931ef6b",
                    machine_id="TRAY-PACK-01",
                    status="OK",
                    occurred_at_utc="2026-09-30T01:02:03+00:00",
                )
            )

            self.assertEqual(run["operator_name"], "Operator A")
            self.assertEqual(submitter.payloads[0]["operatorName"], "Operator A")
            reopened = ProductionRunController(settings, database, submitter)
            self.assertEqual(reopened.summary()["operator_name"], "Operator A")


if __name__ == "__main__":
    unittest.main()

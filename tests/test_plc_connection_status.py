"""Tests for PLC status snapshots and the operator status endpoint."""

import json
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.request import urlopen

from tcp_v2_config import Settings
from tcp_v2_plc import LatchState
from tcp_v2_plc_status import PlcConnectionStatus
from tcp_v2_service import TrayInspectionService
from tcp_v2_web import OperatorWebServer


class FakePlc:
    def __init__(self, connect_result: bool, read_error: Exception | None = None) -> None:
        self.connect_result = connect_result
        self.read_error = read_error

    def connect(self) -> bool:
        return self.connect_result

    def read_latches(self) -> LatchState:
        if self.read_error:
            raise self.read_error
        return LatchState(ok=False, ng=False)

    def close(self) -> None:
        pass


class PlcConnectionStatusTests(unittest.TestCase):
    def test_starts_connecting_then_tracks_last_success_and_failure(self) -> None:
        status = PlcConnectionStatus()
        initial = status.snapshot()
        self.assertEqual(initial["state"], "connecting")
        self.assertFalse(initial["connected"])
        self.assertIsNone(initial["lastSuccessUtc"])

        status.mark_connected()
        connected = status.snapshot()
        self.assertEqual(connected["state"], "connected")
        self.assertTrue(connected["connected"])
        self.assertTrue(str(connected["lastSuccessUtc"]).endswith("Z"))
        self.assertIsNone(connected["lastError"])

        status.mark_disconnected("PLC connection failed")
        disconnected = status.snapshot()
        self.assertEqual(disconnected["state"], "disconnected")
        self.assertFalse(disconnected["connected"])
        self.assertEqual(disconnected["lastError"], "PLC connection failed")
        self.assertEqual(disconnected["lastSuccessUtc"], connected["lastSuccessUtc"])

    def test_poll_loop_marks_connection_failure_for_the_ui(self) -> None:
        status = PlcConnectionStatus()
        service = TrayInspectionService(Settings(), plc_status=status)
        service._plc = FakePlc(connect_result=False)
        try:
            with patch("tcp_v2_service.time.sleep", side_effect=service.stop):
                service.run()
            snapshot = status.snapshot()
            self.assertEqual(snapshot["state"], "disconnected")
            self.assertFalse(snapshot["connected"])
        finally:
            service.close()

    def test_poll_loop_marks_success_only_after_latch_read(self) -> None:
        status = PlcConnectionStatus()
        service = TrayInspectionService(Settings(), plc_status=status)
        service._plc = FakePlc(connect_result=True)
        try:
            with patch("tcp_v2_service.time.sleep", side_effect=service.stop):
                service.run()
            snapshot = status.snapshot()
            self.assertEqual(snapshot["state"], "connected")
            self.assertTrue(snapshot["connected"])
        finally:
            service.close()

    def test_poll_loop_marks_latch_read_error_as_disconnected(self) -> None:
        status = PlcConnectionStatus()
        service = TrayInspectionService(Settings(), plc_status=status)
        service._plc = FakePlc(connect_result=True, read_error=OSError("latch read failed"))
        try:
            with patch("tcp_v2_service.time.sleep", side_effect=service.stop):
                service.run()
            snapshot = status.snapshot()
            self.assertEqual(snapshot["state"], "disconnected")
            self.assertFalse(snapshot["connected"])
            self.assertEqual(snapshot["lastError"], "latch read failed")
        finally:
            service.close()

    def test_operator_api_returns_the_shared_plc_status(self) -> None:
        status = PlcConnectionStatus()
        status.mark_connected()
        server = OperatorWebServer(
            "127.0.0.1", 0, Path(__file__).resolve().parent, None, None, status
        )
        try:
            server.start()
            host, port = server._server.server_address[:2]
            with urlopen(f"http://{host}:{port}/api/plc-status", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["connected"])
            self.assertEqual(payload["state"], "connected")
            self.assertIsNotNone(payload["lastSuccessUtc"])
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()

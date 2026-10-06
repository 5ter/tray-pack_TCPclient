"""Main flow: detect one M7/M8 edge and associate it with the current run."""

import logging
import time
from collections.abc import Callable

from pymodbus.exceptions import ConnectionException, ModbusException

from tcp_v2_config import Settings
from tcp_v2_events import InspectionEvent
from tcp_v2_plc import LatchState, PlcLatchReader
from tcp_v2_plc_status import PlcConnectionStatus


class TrayInspectionService:
    """Coordinates the small modules without containing PLC protocol details."""

    def __init__(
        self,
        settings: Settings,
        event_handler: Callable[[InspectionEvent], None] | None = None,
        camera_mode_handler: Callable[[int | None], None] | None = None,
        plc_status: PlcConnectionStatus | None = None,
    ) -> None:
        if settings.ok_coil_address == settings.ng_coil_address:
            raise ValueError("OK_COIL_ADDRESS and NG_COIL_ADDRESS must be different")
        self._settings = settings
        self._plc = PlcLatchReader(settings)
        self._previous: LatchState | None = None
        self._running = True
        self._event_handler = event_handler
        self._camera_mode_handler = camera_mode_handler
        self._plc_status = plc_status or PlcConnectionStatus()
        self._camera_mode_read_failed = False

    def stop(self, *_: object) -> None:
        self._running = False

    def close(self) -> None:
        self._plc.close()

    def _record(self, status: str) -> None:
        source_coil = self._settings.ok_coil_address if status == "OK" else self._settings.ng_coil_address
        event = InspectionEvent.create(self._settings.machine_id, status)
        logging.info("NEW %s event from M%s", status, source_coil)
        self._handle_event(event)

    def _handle_event(self, event: InspectionEvent) -> None:
        if self._event_handler is None:
            logging.warning("No event handler configured; result was not submitted")
            return
        self._event_handler(event)

    def _refresh_camera_mode(self) -> None:
        if self._camera_mode_handler is None:
            return
        try:
            mode = self._plc.read_camera_mode()
        except (ConnectionException, ModbusException, OSError) as error:
            if not self._camera_mode_read_failed:
                logging.warning("Could not read PLC D1 camera mode: %s", error)
            self._camera_mode_read_failed = True
            self._camera_mode_handler(None)
            return

        if self._camera_mode_read_failed:
            logging.info("PLC D1 camera-mode reading recovered")
        self._camera_mode_read_failed = False
        self._camera_mode_handler(mode)

    def _process_latch_change(self, current: LatchState) -> None:
        if self._previous is None:
            # Synchronize only: a high latch at startup can be an old result.
            self._previous = current
            logging.info("Initial latch state: M7/OK=%s, M8/NG=%s", current.ok, current.ng)
            return

        # OFF -> ON means a new final result since the preceding Modbus poll.
        if current.ok and not self._previous.ok:
            self._record("OK")
        if current.ng and not self._previous.ng:
            self._record("NG")
        if current.ok and current.ng:
            logging.error("M7 and M8 are both ON; investigate the PLC result state")

        self._previous = current

    def run(self) -> None:
        logging.info(
            "Polling PLC %s:%s: M%s=OK, M%s=NG",
            self._settings.plc_ip,
            self._settings.plc_port,
            self._settings.ok_coil_address,
            self._settings.ng_coil_address,
        )
        while self._running:
            try:
                if self._plc.connect():
                    latch_state = self._plc.read_latches()
                    self._plc_status.mark_connected()
                    self._process_latch_change(latch_state)
                    self._refresh_camera_mode()
                else:
                    self._plc_status.mark_disconnected("PLC connection failed")
                    if self._camera_mode_handler is not None:
                        self._camera_mode_handler(None)
            except (ConnectionException, ModbusException, OSError) as error:
                logging.warning("PLC communication error: %s", error)
                self._plc_status.mark_disconnected(str(error))
                if self._camera_mode_handler is not None:
                    self._camera_mode_handler(None)
                self._plc.close()
                time.sleep(self._settings.reconnect_delay_seconds)

            time.sleep(self._settings.poll_interval_seconds)

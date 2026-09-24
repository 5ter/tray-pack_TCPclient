"""Main flow: PLC latch change -> event -> local queue -> optional forwarding."""

import logging
import time
from collections.abc import Callable

from pymodbus.exceptions import ConnectionException, ModbusException

from tcp_v2_config import Settings
from tcp_v2_events import EventOutbox, InspectionEvent
from tcp_v2_plc import LatchState, PlcLatchReader
from tcp_v2_sender import ResultForwarder


class TrayInspectionService:
    """Coordinates the small modules without containing PLC protocol details."""

    def __init__(
        self,
        settings: Settings,
        event_handler: Callable[[InspectionEvent], None] | None = None,
    ) -> None:
        if settings.ok_coil_address == settings.ng_coil_address:
            raise ValueError("OK_COIL_ADDRESS and NG_COIL_ADDRESS must be different")
        self._settings = settings
        self._plc = PlcLatchReader(settings)
        self._outbox = EventOutbox(settings.outbox_path)
        self._forwarder = ResultForwarder(settings)
        self._previous: LatchState | None = None
        self._running = True
        self._last_forward_attempt = 0.0
        self._event_handler = event_handler

    def stop(self, *_: object) -> None:
        self._running = False

    def close(self) -> None:
        self._forwarder.close()
        self._outbox.close()
        self._plc.close()

    def _record(self, status: str) -> None:
        source_coil = self._settings.ok_coil_address if status == "OK" else self._settings.ng_coil_address
        event = InspectionEvent.create(self._settings.machine_id, status, source_coil)
        self._outbox.add(event)
        logging.info("NEW %s event id=%s from M%s", status, event.event_id, source_coil)
        self.handle_event(event)

    def handle_event(self, event: InspectionEvent) -> None:
        """Future phase: perform PC-side Box-ID, print, and database work here.

        For now this only logs. It is intentionally safe: this version cannot
        print a label or alter a Box ID until the product-data contract is added.
        """
        if self._event_handler is None:
            logging.info("Event ready for future PC pipeline: %s", event.status)
            return
        self._event_handler(event)

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

    def _forward_pending_events(self) -> None:
        if not self._settings.forward_results:
            return
        for event in self._outbox.pending():
            try:
                self._forwarder.send(event)
                self._outbox.mark_delivered(event.event_id)
                logging.info("Forwarded event id=%s", event.event_id)
            except OSError as error:
                logging.warning("Result server unavailable; event remains queued: %s", error)
                self._forwarder.close()
                return

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
                    self._process_latch_change(self._plc.read_latches())
            except (ConnectionException, ModbusException, OSError) as error:
                logging.warning("PLC communication error: %s", error)
                self._plc.close()
                time.sleep(self._settings.reconnect_delay_seconds)

            if time.monotonic() - self._last_forward_attempt >= 0.5:
                self._forward_pending_events()
                self._last_forward_attempt = time.monotonic()
            time.sleep(self._settings.poll_interval_seconds)

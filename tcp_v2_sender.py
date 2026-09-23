"""Optional forwarding to the existing TCP result receiver (server.py)."""

import logging
import socket

from tcp_v2_config import Settings
from tcp_v2_events import InspectionEvent


class ResultForwarder:
    """Send newline-delimited JSON to the existing port-3333 receiver."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._socket: socket.socket | None = None

    def send(self, event: InspectionEvent) -> None:
        if self._socket is None:
            logging.info(
                "Connecting to result server at %s:%s",
                self._settings.result_server_ip,
                self._settings.result_server_port,
            )
            self._socket = socket.create_connection(
                (self._settings.result_server_ip, self._settings.result_server_port),
                timeout=self._settings.result_server_timeout_seconds,
            )
        self._socket.sendall(event.as_json_line().encode("utf-8"))

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

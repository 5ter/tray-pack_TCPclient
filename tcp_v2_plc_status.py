"""Thread-safe status snapshot for PLC polling and the operator UI."""

from datetime import datetime, timezone
from threading import Lock


class PlcConnectionStatus:
    """Track whether the latest M7/M8 poll successfully communicated with PLC."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._state = "connecting"
        self._last_success_utc: str | None = None
        self._last_error: str | None = None

    def mark_connected(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._lock:
            self._state = "connected"
            self._last_success_utc = now
            self._last_error = None

    def mark_disconnected(self, error: str) -> None:
        with self._lock:
            self._state = "disconnected"
            self._last_error = error

    def snapshot(self) -> dict[str, str | bool | None]:
        with self._lock:
            return {
                "state": self._state,
                "connected": self._state == "connected",
                "lastSuccessUtc": self._last_success_utc,
                "lastError": self._last_error,
            }

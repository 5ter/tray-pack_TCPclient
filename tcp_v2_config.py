"""Configuration values for tcpClient_v2.

Every value can be overridden through an environment variable. The defaults
match the existing proof-of-concept client.
"""

from dataclasses import dataclass
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _text(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def _integer(name: str, default: int) -> int:
    try:
        return int(_text(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _number(name: str, default: float) -> float:
    try:
        value = float(_text(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _boolean(name: str, default: bool) -> bool:
    value = _text(name, str(default)).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    """Network and polling settings used by the small modules."""

    plc_ip: str = _text("PLC_IP", "192.168.6.6")
    plc_port: int = _integer("PLC_PORT", 502)
    modbus_device_id: int = _integer("MODBUS_DEVICE_ID", 1)
    # Existing main.py uses this convention: Modbus coil 7 = M7; coil 8 = M8.
    ok_coil_address: int = _integer("OK_COIL_ADDRESS", 7)
    ng_coil_address: int = _integer("NG_COIL_ADDRESS", 8)
    poll_interval_seconds: float = _number("POLL_INTERVAL_SECONDS", 0.2)
    plc_timeout_seconds: float = _number("PLC_TIMEOUT_SECONDS", 1.0)
    reconnect_delay_seconds: float = _number("RECONNECT_DELAY_SECONDS", 1.0)
    machine_id: str = _text("MACHINE_ID", "TRAY-PACK-01")
    result_server_ip: str = _text("RESULT_SERVER_IP", "192.168.40.29")
    result_server_port: int = _integer("RESULT_SERVER_PORT", 3168)
    result_server_timeout_seconds: float = _number("RESULT_SERVER_TIMEOUT_SECONDS", 2.0)
    forward_results: bool = _boolean("FORWARD_RESULTS", True)
    outbox_path: Path = Path(_text("OUTBOX_PATH", str(BASE_DIR / "tray_events.sqlite3")))

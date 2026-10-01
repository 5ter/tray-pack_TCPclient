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
    # Xinje XD/XL Modbus maps D0 to holding-register address 0, so D1 is 1.
    camera_mode_register_address: int = _integer("CAMERA_MODE_REGISTER_ADDRESS", 1)
    machine_id: str = _text("MACHINE_ID", "TRAY-PACK-01")
    db_base_url: str = _text("DB_BASE_URL", "http://192.168.40.29:3168")
    db_timeout_seconds: float = _number("DB_TIMEOUT_SECONDS", 5.0)
    result_outbox_path: Path = Path(_text("RESULT_OUTBOX_PATH", str(BASE_DIR / "result_outbox.sqlite3")))
    result_batch_interval_seconds: float = _number("RESULT_BATCH_INTERVAL_SECONDS", 10.0)
    result_batch_size: int = _integer("RESULT_BATCH_SIZE", 100)
    active_run_path: Path = Path(_text("ACTIVE_RUN_PATH", str(BASE_DIR / "active_run.json")))
    camera_tcp_host: str = _text("CAMERA_TCP_HOST", "0.0.0.0")
    camera_tcp_port: int = _integer("CAMERA_TCP_PORT", 5001)
    web_host: str = _text("WEB_HOST", "127.0.0.1")
    web_port: int = _integer("WEB_PORT", 3000)
    web_root: Path = BASE_DIR

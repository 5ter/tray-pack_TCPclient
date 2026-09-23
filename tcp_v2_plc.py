"""The only module that communicates with the PLC.

It reads only M7 (final OK latch) and M8 (final NG latch). It does not read
the HMI register, the mode register, or individual camera inputs.
"""

from dataclasses import dataclass
import logging

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from tcp_v2_config import Settings


@dataclass(frozen=True)
class LatchState:
    """Current state of the final PLC decision latches."""

    ok: bool
    ng: bool


class PlcLatchReader:
    """Connect to the PLC's Modbus TCP server and read M7/M8."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = ModbusTcpClient(
            settings.plc_ip,
            port=settings.plc_port,
            timeout=settings.plc_timeout_seconds,
        )

    def connect(self) -> bool:
        """Connect once. Returns False instead of raising when PLC is unavailable."""
        if self._client.connected:
            return True
        logging.info("Connecting to PLC at %s:%s", self._settings.plc_ip, self._settings.plc_port)
        if not self._client.connect():
            logging.warning("PLC connection failed")
            return False
        logging.info("PLC connected")
        return True

    def read_latches(self) -> LatchState:
        """Read final M7/M8 latches using the configured Modbus addresses."""
        ok_response = self._client.read_coils(
            self._settings.ok_coil_address,
            count=1,
            device_id=self._settings.modbus_device_id,
        )
        if ok_response.isError():
            raise ModbusException(f"Cannot read M7/OK: {ok_response}")

        ng_response = self._client.read_coils(
            self._settings.ng_coil_address,
            count=1,
            device_id=self._settings.modbus_device_id,
        )
        if ng_response.isError():
            raise ModbusException(f"Cannot read M8/NG: {ng_response}")

        return LatchState(ok=bool(ok_response.bits[0]), ng=bool(ng_response.bits[0]))

    def close(self) -> None:
        self._client.close()
